Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like '*ai_video_editor*' -or
    ($_.CommandLine -match 'ingest_worker|reason_worker|render_worker|segment_worker|style_worker')
} | Stop-Process -Force
