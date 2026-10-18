systemContext aura "C1_Context" {
    include *
    autoLayout lr
    title "C1 - AURA system context"
}
container aura "C2_Containers" {
    include operator gui cli capture pythonCapture service inference enhancement evidence state artifacts spools index models auditStore
    autoLayout lr
    title "C2 - AURA processes and data stores"
}
component gui "C3_Desktop" {
    include guiControl guiSdk splitter diagnostics qtAdapters transport artifacts releases
    autoLayout lr
    title "C3 - Desktop interaction, splitting and diagnostics"
}
component cli "C3_Terminal" {
    include commands terminal sdk nativeLauncher transport captureIO
    autoLayout lr
    title "C3 - Terminal controls and the shared SDK"
}
component capture "C3_NativeCapture" {
    include captureIO captureTransport captureCompletion spools transport
    autoLayout lr
    title "C3 - Native capture, durable transport and cleanup"
}
component pythonCapture "C3_PythonCapture" {
    include pythonIO producerSdk transport spools audioOS
    autoLayout lr
    title "C3 - Selectable Python capture producer"
}
component service "C3_Service" {
    include transport sessions live repair health scheduler retention review audit scheduling state artifacts executor reuseProtocol auditStore
    autoLayout lr
    title "C3 - Account service and durable session ownership"
}
component inference "C3_Inference" {
    include executor asr filePipeline postprocess diarization media exportExecution reuseProtocol artifacts models
    autoLayout lr
    title "C3 - Fixed ASR runtime, file processing and optional diarization"
}
component enhancement "C3_Enhancement" {
    include reuseProtocol stream guard reuseModel offline live repair models
    autoLayout lr
    title "C3 - Real-time and offline RE-USE worker internals"
}
component evidence "C3_Evidence" {
    include operator evidenceIndex artifacts index
    autoLayout lr
    title "C3 - Explicit evidence indexing and read-only queries"
}
dynamic aura "DYN_LiveCapture" {
    operator -> cli "Start recording"
    cli -> service "Create session and load fixed ASR"
    cli -> capture "Start capture helper"
    capture -> audioOS "Read selected sources"
    capture -> spools "Persist original frames before upload"
    capture -> service "Send sequence; receive durable ACK"
    service -> artifacts "Persist original PCM"
    service -> state "Commit durable cursor and jobs"
    service -> enhancement "Enhance journal independently"
    service -> inference "Recognize only enhanced VAD ranges"
    inference -> artifacts "Persist live text and segments"
    autoLayout lr
    title "Dynamic - Live capture to persistent text"
}
dynamic aura "DYN_SpeechRepair" {
    service -> artifacts "Compare aligned source and enhanced speech evidence"
    service -> enhancement "Reset once on sustained suppression; continue stream"
    service -> artifacts "Retain unresolved gap and original"
    service -> enhancement "Fresh-state repair: up to two bounded attempts; main stream has priority"
    service -> inference "Submit usable uncovered enhanced ranges only"
    inference -> artifacts "Persist late text without replacing human edits"
    service -> state "Leave submitted overlaps or failed repair pending for review"
    autoLayout lr
    title "Dynamic - Speech protection and bounded live repair"
}
dynamic aura "DYN_StopExport" {
    cli -> service "Request Stop"
    capture -> service "Finish durable final sequence"
    service -> enhancement "Drain current live interval; cancel unfinished repair"
    service -> inference "Drain committed ASR jobs, then export audio only"
    inference -> enhancement "Offline RE-USE of complete original source"
    enhancement -> artifacts "Write exact-length enhanced scratch"
    inference -> artifacts "Normalize, encode, fully decode and atomically publish M4A"
    service -> state "Mark ready; pending review retains original"
    capture -> service "Confirm all frames durable and delivery state"
    capture -> spools "Delete only with authenticated delivery commit"
    autoLayout lr
    title "Dynamic - Stop, audio export and gated cleanup"
}
dynamic aura "DYN_PauseReconnect" {
    cli -> service "Pause current recording"
    capture -> service "Finish boundary and durable cursor"
    service -> enhancement "Flush interval; reset transform and model for next interval"
    cli -> service "Resume recording"
    capture -> spools "Continue original capture journal"
    capture -> service "Reconnect with ownership and returned durable cursor"
    service -> state "Deduplicate acknowledged packets and reject conflicting ownership"
    service -> enhancement "Continue from durable journal without duplicate ASR jobs"
    autoLayout lr
    title "Dynamic - Pause, resume and durable reconnection"
}
dynamic aura "DYN_StoppedRecovery" {
    operator -> cli "Explicitly request recovery after Stop"
    cli -> service "Recover stopped recording, optional language override"
    service -> artifacts "Scan uncovered original speech; preserve saved options and edits"
    service -> enhancement "Fresh-state enhancement with bounded context/retry"
    service -> inference "Recognize only newly usable enhanced gaps"
    inference -> artifacts "Persist recovered machine text and segments"
    service -> state "Resolve only completed gaps; keep review candidates"
    autoLayout lr
    title "Dynamic - Explicit stopped-recording recovery"
}
dynamic aura "DYN_ImportRefine" {
    operator -> cli "Import media or explicitly refine saved audio"
    cli -> service "Upload/select input; request file job"
    service -> inference "Dispatch import/refinement with frozen session options"
    inference -> enhancement "Offline RE-USE of supplied input"
    enhancement -> artifacts "Write enhanced scratch"
    inference -> models "Load fixed ASR and optional punctuation/diarization models"
    inference -> artifacts "Normalize, transcribe, postprocess; refinement uses separate output"
    service -> state "Persist file result without overwriting edited live text"
    autoLayout lr
    title "Dynamic - Imported media and explicit refinement"
}
dynamic aura "DYN_ReviewSearch" {
    operator -> gui "Edit and review transcript"
    gui -> service "Submit current revision"
    service -> artifacts "Atomically save canonical text, segments and review events"
    operator -> evidence "Explicitly rebuild evidence index"
    evidence -> artifacts "Read compatible canonical packages and identity evidence"
    evidence -> index "Rebuild derived FTS5 index"
    operator -> evidence "Search segments or locate audio span"
    evidence -> index "Read-only query"
    autoLayout lr
    title "Dynamic - Review and compatible artifact search"
}
dynamic aura "DYN_Splitting" {
    operator -> gui "Select local media and split settings"
    gui -> artifacts "Read media through FFmpeg; find nearby silence boundaries"
    gui -> artifacts "Write ordered media parts and report paths"
    autoLayout lr
    title "Dynamic - Local audio splitting"
}
deployment aura "LocalGB10" "DEP_LocalGB10" {
    include *
    autoLayout lr
    title "Deployment - Linux GB10 local workstation"
}
deployment aura "SSHClient" "DEP_SSHClient" {
    include *
    autoLayout lr
    title "Deployment - CPU client over OpenSSH to GPU host"
}
deployment aura "WindowsGated" "DEP_WindowsGated" {
    include *
    autoLayout lr
    title "Deployment - Windows source and runtime activation gates"
}
