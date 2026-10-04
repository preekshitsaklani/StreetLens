Attribute VB_Name = "ScenarioRunner"
Option Explicit
' Runs Bear, Base and Bull for every company and writes target, total return and rating to Cover.
' Import: Alt+F11 > File > Import File > ScenarioRunner.bas, then save as .xlsm.

Public Sub RunScenarios()
    Dim tickers As Variant, original As Variant, s As Integer, j As Integer
    tickers = Array("JPM", "GS", "BLK", "STT")
    original = Range("ScenarioSelector").Value
    Application.ScreenUpdating = False
    On Error GoTo CleanUp
    For s = 1 To 3
        Range("ScenarioSelector").Value = s
        Application.Calculate
        For j = 0 To UBound(tickers)
            Range("ScenarioOut").Offset(s, 1 + 3 * j).Value = Range("TP_" & tickers(j)).Value
            Range("ScenarioOut").Offset(s, 2 + 3 * j).Value = Range("TR_" & tickers(j)).Value
            Range("ScenarioOut").Offset(s, 3 + 3 * j).Value = Range("RATING_" & tickers(j)).Value
        Next j
    Next s
CleanUp:
    Range("ScenarioSelector").Value = original
    Application.Calculate
    Application.ScreenUpdating = True
    If Err.Number <> 0 Then MsgBox "Stopped: " & Err.Description, vbExclamation Else MsgBox "Scenarios refreshed.", vbInformation
End Sub


Public Sub ExportScenariosForTableau()
    ' Writes the Cover scenario table to scenarios_excel.csv next to the workbook, for Tableau.
    Dim f As Integer, r As Long, c As Long, line As String, path As String
    path = ThisWorkbook.Path & Application.PathSeparator & "scenarios_excel.csv"
    f = FreeFile
    Open path For Output As #f
    For r = 0 To 3
        line = ""
        For c = 0 To 12
            line = line & IIf(c > 0, ",", "") & CStr(Range("ScenarioOut").Offset(r, c).Value)
        Next c
        Print #f, line
    Next r
    Close #f
    MsgBox "Exported to " & path, vbInformation
End Sub
