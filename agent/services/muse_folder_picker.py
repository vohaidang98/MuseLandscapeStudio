"""Windows folder dialog; called on demand by the local authenticated UI."""
import asyncio
import base64
import os
import subprocess


async def choose(initial):
    # pywebview uses the native Vista IFileDialog with FOS_PICKFOLDERS:
    # Explorer navigation, address bar, search and a Select Folder button.
    import webview
    if webview.windows:
        result = await asyncio.to_thread(
            webview.windows[0].create_file_dialog, webview.FOLDER_DIALOG,
            directory=str(initial))
        return result[0] if result else ''
    script = '''
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = 'Chọn thư mục lưu ảnh và video Muse'
$dialog.InitialDirectory = $env:MUSE_FOLDER_INITIAL
$dialog.CheckFileExists = $false
$dialog.AddExtension = $false
$flags = [Reflection.BindingFlags]'Instance, Public, NonPublic'
$assembly = [System.Windows.Forms.FileDialog].Assembly
$native = $assembly.GetType('System.Windows.Forms.FileDialogNative+IFileDialog')
$nativeDialog = $dialog.GetType().GetMethod('CreateVistaDialog', $flags).Invoke($dialog, @())
$dialog.GetType().GetMethod('OnBeforeVistaDialog', $flags).Invoke($dialog, @($nativeDialog)) | Out-Null
$options = [System.Windows.Forms.FileDialog].GetMethod('GetOptions', $flags).Invoke($dialog, @())
$native.GetMethod('SetOptions').Invoke($nativeDialog, @([uint32]([uint32]$options -bor 0x20))) | Out-Null
$eventsType = $assembly.GetType('System.Windows.Forms.FileDialog+VistaDialogEvents')
$constructor = $eventsType.GetConstructor($flags, $null, [Type[]]@([System.Windows.Forms.FileDialog]), $null)
$events = $constructor.Invoke(@($dialog))
$arguments = [object[]]@($events, [uint32]0)
$native.GetMethod('Advise').Invoke($nativeDialog, $arguments) | Out-Null
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
try {
  $result = $native.GetMethod('Show').Invoke($nativeDialog, @($owner.Handle))
  if ($result -eq 0) { [Console]::Write($dialog.FileName) }
} finally {
  $native.GetMethod('Unadvise').Invoke($nativeDialog, @([uint32]$arguments[1])) | Out-Null
  $dialog.Dispose(); $owner.Dispose()
}
'''
    env = dict(os.environ, MUSE_FOLDER_INITIAL=str(initial))
    def run():
        try:
            result = subprocess.run(
                ['powershell.exe', '-NoProfile', '-STA', '-EncodedCommand',
                 base64.b64encode(script.encode('utf-16le')).decode('ascii')],
                env=env, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=300, check=True)
            return result.stdout.decode('utf-8-sig').strip()
        except (OSError, subprocess.SubprocessError):
            raise ValueError('Không mở được cửa sổ chọn thư mục. Bạn có thể nhập đường dẫn rồi bấm Lưu thư mục.') from None
    return await asyncio.to_thread(run)

