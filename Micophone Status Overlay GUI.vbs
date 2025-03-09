' This VBScript installs necessary imports on first launch and opens the Microphone Status Overlay GUI

' Create objects for the shell and filesystem
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Change directory to the parent directory
shell.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)

' Flag to determine if we should launch the GUI
Dim launchGUI
launchGUI = True

' Check if requirements.txt exists
If fso.FileExists("docs/requirements.txt") Then
    ' Read the contents of requirements.txt
    Set file = fso.OpenTextFile("docs/requirements.txt", 1)
    requirements = ""
    Do Until file.AtEndOfStream
        requirements = requirements & "    " & file.ReadLine & vbNewLine
    Loop
    file.Close
    
    message = "    The following Python imports will be installed:" & vbNewLine & vbNewLine
    message = message & requirements & vbNewLine
    message = message & "    Would you like to proceed with the installation?"
    
    ' Prompt user for confirmation
    response = MsgBox(message, vbYesNo + vbQuestion, "Microphone Status Overlay Imports Installer")
    
    If response = vbYes Then        
        ' Install imports silently
        returnCode = shell.Run("cmd /c pip install -r docs/requirements.txt", 0, True)
        
        ' Check installation result
        If returnCode = 0 Then
            ' Rename requirements.txt
            fso.MoveFile "docs/requirements.txt", "docs/requirements_installed.txt"
        Else
            MsgBox "    There was an error installing the imports. The GUI will not be launched.", vbExclamation, "Microphone Status Overlay Imports Installer"
            launchGUI = False
        End If
    Else
        MsgBox "    Installation cancelled. The GUI will not be launched.", vbExclamation, "Microphone Status Overlay Imports Installer"
        launchGUI = False
    End If
End If

' Launch GUI if the flag is still True
If launchGUI Then
    shell.Run "pythonw src/overlay_GUI.py", 0, False
End If
