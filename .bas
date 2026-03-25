Sub Macro3_Modified()
    
    
    ' Performance: disable screen updating and auto calculation
    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual
    
    ' -- Cleanup existing queries --
    On Error Resume Next
    Dim i As Long, queriesRemoved As Long
    queriesRemoved = 0
    For i = ActiveWorkbook.Queries.Count To 1 Step -1
        ActiveWorkbook.Queries(i).Delete
        queriesRemoved = queriesRemoved + 1
    Next i
    On Error GoTo 0
    
    ' -- File selection dialog --
    Dim fd As FileDialog
    Dim pdfPath As String
    Set fd = Application.FileDialog(msoFileDialogFilePicker)
    With fd
        .Title = "Select PDF File to Extract Tables From"
        .AllowMultiSelect = False
        .Filters.Clear
        .Filters.Add "PDF Files", "*.pdf"
        If .Show = True Then
            pdfPath = .SelectedItems(1)
            ' Ask for specific page number AFTER file is selected
            Dim selectedPageInput As Variant
            selectedPageInput = Application.InputBox( _
                Prompt:="Enter the page number to extract tables from:", _
                Title:="Select Page", Type:=1)
            If selectedPageInput = False Then
                MsgBox "Operation canceled by user.", vbExclamation
                Exit Sub
            End If
            If Not IsNumeric(selectedPageInput) Or selectedPageInput < 1 Then
                MsgBox "Invalid page number entered. Please enter a positive number.", vbCritical
                Exit Sub
            End If
            Dim selectedPage As Long
            selectedPage = CLng(selectedPageInput)
        Else
            MsgBox "No file selected. Operation canceled.", vbExclamation
            GoTo Cleanup
        End If
    End With
    
    ' -- Create temporary Power Query to list all tables in the PDF --
    On Error Resume Next
    ActiveWorkbook.Queries.Add Name:="TempPdfQuery", Formula:= _
        "let" & Chr(13) & Chr(10) & _
        "    Source = Pdf.Tables(File.Contents(""" & pdfPath & """), [Implementation=""1.3""])" & Chr(13) & Chr(10) & _
        "in" & Chr(13) & Chr(10) & _
        "    Source"
    On Error GoTo 0
    
    ' Create a connection to get table info
    Dim conn As WorkbookConnection
    Set conn = ActiveWorkbook.Connections.Add2( _
        Name:="TempConnection", _
        Description:="", _
        ConnectionString:="OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=$Workbook$;Location=""TempPdfQuery"";", _
        CommandText:="SELECT * FROM [TempPdfQuery]", _
        lCmdtype:=xlCmdSql, _
        CreateModelConnection:=False, _
        ImportRelationships:=False)
    
    ' Load the table info to a hidden worksheet "TempSheet"
    Dim wsTemp As Worksheet
    Set wsTemp = ActiveWorkbook.Worksheets.Add
    wsTemp.Name = "TempSheet"
    Dim qt As QueryTable
    Set qt = wsTemp.QueryTables.Add(Connection:=conn, Destination:=wsTemp.Range("A1"))
    qt.RefreshStyle = xlOverwriteCells
    qt.Refresh False
    
    ' Determine number of tables and validate selected page
    Dim tableCount As Long
    tableCount = Application.WorksheetFunction.CountA(wsTemp.Range("A:A"))
    If tableCount = 0 Then
        MsgBox "No tables found in the selected PDF.", vbExclamation
        GoTo Cleanup
    End If
    
    ' Find distinct pages from the temp sheet (assume page in Column2)
    Dim pageDict As Object
    Set pageDict = CreateObject("Scripting.Dictionary")
    Dim r As Long
    Dim tablePage As Long
    For r = 1 To tableCount
        
        If IsNumeric(wsTemp.Cells(r, 2).Value) Then
            tablePage = CLng(wsTemp.Cells(r, 2).Value)
            If Not pageDict.Exists(tablePage) Then
                pageDict.Add tablePage, 1
            End If
        End If

    Next r
    ' Validate selected page exists
    If Not pageDict.Exists(selectedPage) Then
        MsgBox "Page " & selectedPage & " not found in PDF tables. Please enter a valid page.", vbExclamation
        GoTo Cleanup
    End If
    
    ' Inform user of number of tables (optional)
    MsgBox "Found " & tableCount & " tables in the PDF. Extracting now...", vbInformation
    
    ' Prepare sheet for consolidated tables on the selected page
    Dim pageSheetName As String
    pageSheetName = "Page_" & selectedPage & "_Tables"
    Dim pageSheet As Worksheet
    On Error Resume Next
    Set pageSheet = ThisWorkbook.Worksheets(pageSheetName)
    On Error GoTo 0
    If Not pageSheet Is Nothing Then
        Application.DisplayAlerts = False
        pageSheet.Delete
        Application.DisplayAlerts = True
    End If
    Set pageSheet = ThisWorkbook.Worksheets.Add
    pageSheet.Name = pageSheetName
    
    ' Dictionary to track table index per page for naming
    Dim pageTableCount As Object
    Set pageTableCount = CreateObject("Scripting.Dictionary")
    
    ' Track performance time
    Dim tStart As Double, tElapsed As Double
    tStart = Timer
    
    ' Loop through each table ID and extract
    For r = 1 To tableCount
        tableId = wsTemp.Cells(r, 1).Value
        tablePage = wsTemp.Cells(r, 2).Value
        
        ' Decide mode based on page
        Dim consolidateMode As Boolean
        If tablePage = selectedPage Then
            consolidateMode = True
        Else
            consolidateMode = False
        End If
        
        ' Build a unique query name including page
        Dim queryName As String
        queryName = tableId & " (Page " & tablePage & ")"
        
        ' Add Power Query for this specific table
        ActiveWorkbook.Queries.Add Name:=queryName, Formula:= _
            "let" & Chr(13) & Chr(10) & _
            "    Source = Pdf.Tables(File.Contents(""" & pdfPath & """), [Implementation=""1.3""])," & Chr(13) & Chr(10) & _
            "    " & tableId & " = Source{[Id=""" & tableId & """]}[Data]," & Chr(13) & Chr(10) & _
            "    #""Changed Type"" = Table.TransformColumnTypes(" & tableId & ",{{""Column1"", type text}, {""Column2"", type text}})" & Chr(13) & Chr(10) & _
            "in" & Chr(13) & Chr(10) & _
            "    #""Changed Type"""
        
        If consolidateMode Then
            ' **Consolidate Mode**: Append this table to the consolidated sheet
            Dim destCell As Range
            If pageSheet.ListObjects.Count = 0 Then
                ' First table on this page: start at A1
                Set destCell = pageSheet.Range("A1")
            Else
                ' Find last row of existing tables and skip 2 rows
                lastRow = pageSheet.Cells(pageSheet.Rows.Count, 1).End(xlUp).Row
                Set destCell = pageSheet.Cells(lastRow + 3, 1)
            End If
            
            ' Create a table from the query on the consolidated sheet
            Dim lo1 As ListObject
            Set lo1 = pageSheet.ListObjects.Add(SourceType:=0, _
                Source:="OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=$Workbook$;Location=""" & queryName & """;", _
                Destination:=destCell)
            
            With lo1.QueryTable
                .CommandType = xlCmdSql
                .CommandText = Array("SELECT * FROM [" & queryName & "]")
                .RowNumbers = False
                .PreserveFormatting = True
                .RefreshOnFileOpen = False
                .BackgroundQuery = False
                .RefreshStyle = xlInsertDeleteCells
                .AdjustColumnWidth = True
                .SaveData = True
                .Refresh False
            End With

            ' Rename the table for clarity
            lo1.Name = Replace(tableId, " ", "_") & "_Page_" & tablePage

            
        Else
            ' **Single-Table Mode**: Extract each table to its own worksheet
            If Not pageTableCount.Exists(tablePage) Then
                pageTableCount.Add tablePage, 1
            Else
                pageTableCount(tablePage) = pageTableCount(tablePage) + 1
            End If
            Dim sheetName As String
            sheetName = "Page_" & tablePage & "_Table_" & pageTableCount(tablePage)
            
            ' Check if a sheet with this name already exists (to avoid errors)
            Dim sht As Worksheet
            On Error Resume Next
            Set sht = ThisWorkbook.Worksheets(sheetName)
            On Error GoTo 0
            If Not sht Is Nothing Then
                Application.DisplayAlerts = False
                sht.Delete
                Application.DisplayAlerts = True
            End If
            
            ' Add new worksheet for this table
            ActiveWorkbook.Worksheets.Add
            ActiveSheet.Name = sheetName
            
            ' Create a table from the query on the new sheet
            Dim lo As ListObject
            Set lo = ActiveSheet.ListObjects.Add(SourceType:=0, Source:= _
                "OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=$Workbook$;Location=""" & queryName & """;", _
                Destination:=Range("$A$1"))

            With lo.QueryTable
                .CommandType = xlCmdSql
                .CommandText = Array("SELECT * FROM [" & queryName & "]")
                .RowNumbers = False
                .PreserveFormatting = True
                .RefreshOnFileOpen = False
                .BackgroundQuery = False
                .RefreshStyle = xlInsertDeleteCells
                .AdjustColumnWidth = True
                .SaveData = True
                .Refresh False
            End With

            ' Optional: rename table
            lo.Name = Replace(tableId, " ", "_") & "_Page_" & tablePage & "_Table"

        End If
        
        ' Update status and allow interruption
        Application.StatusBar = "Processed table " & r & " of " & tableCount & ": " & queryName
        If r Mod 10 = 0 Then DoEvents  ' Keep Excel responsive
    Next r
    
    ' All tables processed
    tElapsed = Timer - tStart
    Application.StatusBar = False
    MsgBox "Extraction complete. " & tableCount & " tables extracted in " & _
           Format(tElapsed, "0.00") & " seconds.", vbInformation

Cleanup:
    ' Remove temporary connections and worksheets
    On Error Resume Next
    conn.Delete
    ActiveWorkbook.Queries("TempPdfQuery").Delete
    wsTemp.Delete
    ' Restore application settings
    Application.ScreenUpdating = True
    Application.Calculation = xlCalculationAutomatic
End Sub


