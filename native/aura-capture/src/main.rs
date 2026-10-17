//! Linux capture and durable replay; CUDA and session ownership remain in AURA.
use anyhow::{bail, Context, Result};
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    fs::{self, File, OpenOptions},
    io::{BufRead, Read, Seek, SeekFrom, Write},
    os::unix::fs::PermissionsExt,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::Duration,
};
use tokio_tungstenite::{
    connect_async,
    tungstenite::{client::IntoClientRequest, Message},
};

const FRAME: usize = 960;
const WINDOW: u64 = 32;
#[derive(Clone, Deserialize)]
struct Connection {
    url: String,
    token: String,
}
#[derive(Clone, Deserialize, Serialize)]
struct Source {
    name: String,
    track: String,
}
#[derive(Deserialize)]
struct Init {
    version: u32,
    connection: Connection,
    session_id: String,
    directory: PathBuf,
    sources: Vec<Source>,
    #[serde(default)]
    input_pcm: Option<PathBuf>,
    #[serde(default)]
    stop_after_ms: Option<u64>,
}
#[derive(Serialize, Deserialize)]
struct Manifest {
    version: u32,
    producer_id: String,
    tracks: Vec<String>,
    base_sequence: u64,
}
struct Capture {
    stopped: Arc<AtomicBool>,
    eof: Arc<AtomicBool>,
    frames: Arc<AtomicU64>,
    error: Arc<Mutex<Option<String>>>,
    children: Arc<Mutex<Vec<Child>>>,
    thread: Option<std::thread::JoinHandle<()>>,
}
impl Capture {
    fn new(frames: u64) -> Self {
        Self {
            stopped: Arc::new(AtomicBool::new(true)),
            eof: Arc::new(AtomicBool::new(false)),
            frames: Arc::new(AtomicU64::new(frames)),
            error: Arc::new(Mutex::new(None)),
            children: Arc::new(Mutex::new(vec![])),
            thread: None,
        }
    }
    fn stop(&mut self) {
        self.stopped.store(true, Ordering::Release);
        for child in self.children.lock().unwrap().iter_mut() {
            let _ = child.kill();
        }
        if let Some(handle) = self.thread.take() {
            let _ = handle.join();
        }
        for mut child in self.children.lock().unwrap().drain(..) {
            let _ = child.wait();
        }
    }
    fn start(&mut self, cfg: &Init, tracks: &[String]) -> Result<()> {
        if self.thread.is_some() || self.eof.load(Ordering::Acquire) {
            return Ok(());
        }
        self.stopped.store(false, Ordering::Release);
        let mut readers: Vec<Box<dyn Read + Send>> = vec![];
        if let Some(path) = &cfg.input_pcm {
            let mut file = File::open(path)?;
            file.seek(SeekFrom::Start(
                self.frames.load(Ordering::Acquire) * FRAME as u64,
            ))?;
            readers.push(Box::new(file));
        } else {
            for source in &cfg.sources {
                let mut child = Command::new("parec")
                    .args([
                        "--device",
                        &source.name,
                        "--format",
                        "s16le",
                        "--rate",
                        "16000",
                        "--channels",
                        "1",
                        "--latency-msec",
                        "30",
                    ])
                    .stdout(Stdio::piped())
                    .stderr(Stdio::piped())
                    .spawn()
                    .context("start parec")?;
                readers.push(Box::new(child.stdout.take().unwrap()));
                let stderr = child.stderr.take().unwrap();
                std::thread::spawn(move || {
                    let mut r = stderr;
                    let mut buffer = [0u8; 1024];
                    while let Ok(n) = r.read(&mut buffer) {
                        if n == 0 {
                            break;
                        }
                    }
                });
                self.children.lock().unwrap().push(child);
            }
        }
        if readers.is_empty() {
            bail!("No capture sources selected");
        }
        let mut spool = OpenOptions::new()
            .create(true)
            .append(true)
            .open(cfg.directory.join("frames.pcm"))?;
        let directory = cfg.directory.clone();
        let stopped = self.stopped.clone();
        let frames = self.frames.clone();
        let eof = self.eof.clone();
        let error = self.error.clone();
        let fixture = cfg.input_pcm.is_some();
        let count = tracks.len();
        self.thread = Some(std::thread::spawn(move || {
            let result = (|| -> Result<()> {
                let mut last_sync = std::time::Instant::now();
                while !stopped.load(Ordering::Acquire) {
                    if frames.load(Ordering::Acquire).is_multiple_of(34) {
                        check_space(&directory)?;
                    }
                    let mut raw = Vec::new();
                    for reader in &mut readers {
                        let mut frame = vec![0u8; FRAME];
                        if let Err(e) = reader.read_exact(&mut frame) {
                            if stopped.load(Ordering::Acquire) {
                                return Ok(());
                            }
                            if fixture && e.kind() == std::io::ErrorKind::UnexpectedEof {
                                eof.store(true, Ordering::Release);
                                return Ok(());
                            }
                            return Err(e).context("audio source ended before a complete frame");
                        }
                        raw.push(frame);
                    }
                    if stopped.load(Ordering::Acquire) {
                        break;
                    }
                    let mixed = if raw.len() == 1 {
                        raw[0].clone()
                    } else {
                        mix(&raw)
                    };
                    spool.write_all(&mixed)?;
                    if count > 1 {
                        for frame in &raw {
                            spool.write_all(frame)?;
                        }
                    }
                    frames.fetch_add(1, Ordering::Release);
                    if last_sync.elapsed() >= Duration::from_millis(250) {
                        spool.sync_data()?;
                        last_sync = std::time::Instant::now();
                    }
                    if fixture {
                        std::thread::sleep(Duration::from_millis(30));
                    }
                }
                Ok(())
            })();
            if let Err(e) = result.and_then(|_| Ok(spool.sync_all()?)) {
                *error.lock().unwrap() = Some(format!("{e:#}"));
            }
        }));
        Ok(())
    }
}
impl Drop for Capture {
    fn drop(&mut self) {
        self.stop();
    }
}
fn check_space(path: &std::path::Path) -> Result<()> {
    use std::os::unix::ffi::OsStrExt;
    let path = std::ffi::CString::new(path.as_os_str().as_bytes())?;
    let mut stat = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    // statvfs fills the output on success; the CString outlives the call.
    if unsafe { libc::statvfs(path.as_ptr(), stat.as_mut_ptr()) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let stat = unsafe { stat.assume_init() };
    if (stat.f_bavail as u128) * (stat.f_frsize as u128) < (1u128 << 30) {
        bail!("Less than 1 GiB free: capture stopped; local audio retained");
    }
    Ok(())
}
fn mix(raw: &[Vec<u8>]) -> Vec<u8> {
    let samples: Vec<Vec<f32>> = raw
        .iter()
        .map(|f| {
            f.as_chunks::<2>()
                .0
                .iter()
                .map(|b| i16::from_le_bytes([b[0], b[1]]) as f32)
                .collect()
        })
        .collect();
    let rms: Vec<f32> = samples
        .iter()
        .map(|s| (s.iter().map(|v| v * v).sum::<f32>() / 480.).sqrt())
        .collect();
    let active: Vec<usize> = (0..rms.len()).filter(|&i| rms[i] >= 80.).collect();
    if active.is_empty() {
        return vec![0; FRAME];
    }
    let target = active.iter().map(|&i| rms[i]).sum::<f32>() / active.len() as f32;
    let mut mixed = vec![0f32; 480];
    for &i in &active {
        let gain = if active.len() == 1 {
            1.
        } else {
            (target / rms[i]).clamp(0.5, 3.)
        };
        for (out, v) in mixed.iter_mut().zip(&samples[i]) {
            *out += v * gain / active.len() as f32;
        }
    }
    let gain = if active.len() > 1 { 0.8 } else { 1. };
    mixed
        .iter()
        .flat_map(|v| ((v * gain).clamp(-32768., 32767.) as i16).to_le_bytes())
        .collect()
}
fn event(value: Value) {
    println!("{value}");
}
fn command(name: &str, args: Value) -> Message {
    Message::Text(
        json!({"version":1,"id":uuid::Uuid::new_v4().to_string(),"command":name,"args":args})
            .to_string()
            .into(),
    )
}
fn result(message: Message) -> Result<Value> {
    let value: Value = serde_json::from_str(message.to_text()?)?;
    if let Some(error) = value.get("error") {
        bail!("service: {error}");
    }
    Ok(value["result"].clone())
}
fn cleanup_spool(directory: &std::path::Path) -> Result<()> {
    // Called only after authenticated delivery-commit evidence from the owner.
    for name in ["frames.pcm", "manifest.json"] {
        let path = directory.join(name);
        if path.exists() {
            fs::remove_file(path)?;
        }
    }
    fs::File::open(directory)?.sync_all()?;
    Ok(())
}

async fn run(cfg: Init, mut updates: tokio::sync::mpsc::Receiver<Connection>) -> Result<()> {
    if cfg.version != 1 {
        bail!("Unsupported helper initialization version");
    }
    fs::create_dir_all(&cfg.directory)?;
    fs::set_permissions(&cfg.directory, fs::Permissions::from_mode(0o700))?;
    use std::os::fd::AsRawFd;
    let owner = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(false)
        .open(cfg.directory.join("capture.lock"))?;
    // Hold the descriptor for this run; two helpers must never append to one spool.
    if unsafe { libc::flock(owner.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        bail!("Another capture helper owns this local spool");
    }
    let mut tracks = vec!["mixed".to_string()];
    if cfg.sources.len() > 1 {
        tracks.extend(cfg.sources.iter().map(|s| s.track.clone()));
    }
    let manifest_path = cfg.directory.join("manifest.json");
    let existing: Option<Manifest> = if manifest_path.exists() {
        Some(serde_json::from_slice(&fs::read(&manifest_path)?)?)
    } else {
        None
    };
    if existing.as_ref().is_some_and(|m| m.tracks != tracks) {
        bail!("Saved spool uses different tracks");
    }
    let mut manifest = existing.unwrap_or(Manifest {
        version: 1,
        producer_id: uuid::Uuid::new_v4().to_string(),
        tracks: tracks.clone(),
        base_sequence: 0,
    });
    let mut spool = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(cfg.directory.join("frames.pcm"))?;
    fs::set_permissions(
        cfg.directory.join("frames.pcm"),
        fs::Permissions::from_mode(0o600),
    )?;
    let width = FRAME * tracks.len();
    let frames = spool.metadata()?.len() / width as u64;
    spool.set_len(frames * width as u64)?;
    let mut capture = Capture::new(frames);
    if let Some(ms) = cfg.stop_after_ms {
        let stopped = capture.stopped.clone();
        let eof = capture.eof.clone();
        let children = capture.children.clone();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(ms)).await;
            eof.store(true, Ordering::Release);
            stopped.store(true, Ordering::Release);
            for child in children.lock().unwrap().iter_mut() {
                let _ = child.kill();
            }
        });
    }
    let mut connection = cfg.connection.clone();
    let mut backoff = 1u64;
    let deadline = cfg
        .stop_after_ms
        .map(|ms| tokio::time::Instant::now() + Duration::from_millis(ms));
    let mut forced_stop = false;
    loop {
        while let Ok(c) = updates.try_recv() {
            connection = c;
        }
        if deadline.is_some_and(|d| tokio::time::Instant::now() >= d) {
            forced_stop = true;
            capture.stop();
        }
        let attempt: Result<bool> = async {
            let mut request = connection.url.clone().into_client_request()?;
            request.headers_mut().insert("Authorization",format!("Bearer {}",connection.token).parse()?);
            let (mut ws,_) = tokio::time::timeout(Duration::from_secs(10),connect_async(request)).await??;
            ws.send(command("audio.open",json!({"session_id":cfg.session_id,"tracks":tracks,"stream_version":2,"producer_id":manifest.producer_id}))).await?;
            let opened = result(tokio::time::timeout(Duration::from_secs(30),ws.next()).await?.context("connection ended")??)?;
            let mut ack = opened["input_sequence"].as_u64().context("missing sequence")?;
            if !manifest_path.exists() {
                manifest.base_sequence = ack;
                let mut f = OpenOptions::new().write(true).create_new(true).open(&manifest_path)?;
                fs::set_permissions(&manifest_path,fs::Permissions::from_mode(0o600))?;
                serde_json::to_writer(&mut f,&manifest)?; f.sync_all()?;
            }
            let mut sent = ack;
            let requires_commit = opened["enhancement"]["strategy"].as_str() == Some("reuse-v1");
            if requires_commit && opened["delivery_committed"].as_bool() == Some(true) {
                capture.stop(); cleanup_spool(&cfg.directory)?;
                event(json!({"event":"completed","durable_sequence":ack})); return Ok(true);
            }
            if matches!(opened["state"].as_str(), Some("ready" | "draining" | "exporting")) && ack == manifest.base_sequence + capture.frames.load(Ordering::Acquire)
                && (!requires_commit || opened["delivery_committed"].as_bool() == Some(true)) {
                capture.stop();
                if requires_commit { cleanup_spool(&cfg.directory)?; }
                event(json!({"event":"completed","durable_sequence":ack})); return Ok(true);
            }
            if ack < manifest.base_sequence || ack > manifest.base_sequence + capture.frames.load(Ordering::Acquire) { bail!("Server cursor is outside the local recovery spool"); }
            let mut state = opened["state"].as_str().unwrap_or("failed").to_string();
            event(json!({"event":"connected","durable_sequence":ack,"state":state}));
            backoff = 1;
            let (mut write, mut read) = ws.split();
            let mut tick = tokio::time::interval(Duration::from_millis(10));
            let mut next_status = tokio::time::Instant::now(); let mut finishing = matches!(state.as_str(), "draining" | "exporting");
            let mut pause_finishing = false;
            let mut last_reply = tokio::time::Instant::now();
            let mut last_send = tokio::time::Instant::now();
            loop {
                tokio::select! {
                    update = updates.recv(), if !updates.is_closed() => { if let Some(c) = update { connection = c; bail!("transport renewed"); } }
                    message = read.next() => {
                        let message = message.context("audio connection closed")??;
                        if message.is_ping() || message.is_pong() { continue; }
                        let value = result(message)?;
                        last_reply = tokio::time::Instant::now();
                        if let Some(n) = value["input_sequence"].as_u64() { if n < ack || n > sent { bail!("Invalid acknowledgement cursor"); } ack = n; }
                        if let Some(s) = value["state"].as_str() { state = s.to_string(); }
                        if matches!(state.as_str(),"draining"|"exporting"|"ready") && (finishing || state == "ready")
                            && (!requires_commit || value["delivery_committed"].as_bool() == Some(true)) {
                            capture.stop();
                            if requires_commit { cleanup_spool(&cfg.directory)?; }
                            event(json!({"event":"completed","durable_sequence":ack})); return Ok(true);
                        }
                        if state == "paused" || (pause_finishing && state == "recording") { finishing = false; pause_finishing = false; }
                    }
                    _ = tokio::signal::ctrl_c() => { forced_stop = true; capture.stop(); }
                    _ = tick.tick() => {
                        if deadline.is_some_and(|d|tokio::time::Instant::now() >= d) { forced_stop = true; }
                        if let Some(error) = capture.error.lock().unwrap().clone() { bail!("capture: {error}"); }
                        if matches!(state.as_str(),"failed"|"recoverable"|"ready") { capture.stop(); bail!("Session stopped accepting audio: {state}"); }
                        if state == "recording" && !forced_stop { capture.start(&cfg,&tracks)?; }
                        if forced_stop || state != "recording" { capture.stop(); }
                        let produced = manifest.base_sequence + capture.frames.load(Ordering::Acquire);
                        if !finishing && sent < produced && sent - ack < WINDOW && state != "paused"
                            && (produced-sent >= 4 || last_send.elapsed() >= Duration::from_millis(120) || state != "recording" || capture.eof.load(Ordering::Acquire)) {
                            let n = (produced-sent).min(4).min(WINDOW-(sent-ack));
                            let mut packet = vec![0u8;8+n as usize*width]; packet[..8].copy_from_slice(&sent.to_le_bytes());
                            spool.seek(SeekFrom::Start((sent-manifest.base_sequence)*width as u64))?;
                            spool.read_exact(&mut packet[8..])?;
                            tokio::time::timeout(Duration::from_secs(10), write.send(Message::Binary(packet.into()))).await??; sent += n; last_send = tokio::time::Instant::now();
                        }
                        if !finishing && ack == produced && (forced_stop || capture.eof.load(Ordering::Acquire) || matches!(state.as_str(),"pausing"|"stopping")) {
                            let action = if state == "pausing" && !forced_stop {"pause"} else {"stop"};
                            pause_finishing = action == "pause";
                            tokio::time::timeout(Duration::from_secs(10), write.send(command("audio.finish",json!({"sequence":ack,"action":action})))).await??; finishing = true;
                        }
                        if tokio::time::Instant::now() >= next_status {
                            tokio::time::timeout(Duration::from_secs(10), write.send(command("audio.status",json!({"captured_sequence":produced,"sent_sequence":sent})))).await??;
                            event(json!({"event":"progress","captured_frames":produced,"durable_frames":ack,"pending_frames":produced-ack,"state":state}));
                            next_status = tokio::time::Instant::now()+Duration::from_millis(250);
                        }
                        if last_reply.elapsed() > Duration::from_secs(30) { bail!("Audio acknowledgement watchdog expired"); }
                    }
                }
            }
        }.await;
        match attempt {
            Ok(true) => return Ok(()),
            Ok(false) => unreachable!(),
            Err(error) => {
                if capture.error.lock().unwrap().is_some()
                    || error.to_string().starts_with("service:")
                    || error.to_string().starts_with("Server cursor")
                    || error
                        .to_string()
                        .starts_with("Invalid acknowledgement cursor")
                    || error
                        .to_string()
                        .starts_with("Session stopped accepting audio")
                {
                    capture.stop();
                    return Err(error);
                }
                event(
                    json!({"event":"reconnecting","detail":error.to_string(),"pending_frames":capture.frames.load(Ordering::Acquire)}),
                );
                tokio::select! { _ = tokio::time::sleep(Duration::from_secs(backoff)) => {}, c=updates.recv(), if !updates.is_closed() => {if let Some(c)=c {connection=c;}}, _=tokio::signal::ctrl_c() => {forced_stop=true;capture.stop();} }
                backoff = (backoff * 2).min(10);
            }
        }
    }
}
#[tokio::main]
async fn main() {
    if std::env::args().any(|a| a == "--version") {
        event(
            json!({"name":"aura-capture","version":env!("CARGO_PKG_VERSION"),"initialization_version":1,"audio_stream_version":2}),
        );
        return;
    }
    let result: Result<()> = async {
        let mut initial = String::new();
        std::io::stdin().read_line(&mut initial)?;
        let cfg: Init = serde_json::from_str(&initial)?;
        let (tx, rx) = tokio::sync::mpsc::channel(2);
        // A detached OS reader doesn't keep Tokio's blocking pool alive at shutdown.
        std::thread::spawn(move || {
            for line in std::io::stdin().lock().lines() {
                let Ok(line) = line else {
                    break;
                };
                if let Ok(c) = serde_json::from_str::<Connection>(&line) {
                    if tx.blocking_send(c).is_err() {
                        break;
                    }
                }
            }
        });
        run(cfg, rx).await
    }
    .await;
    if let Err(e) = result {
        event(json!({"event":"failed","error":format!("{e:#}")}));
        std::process::exit(1);
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn silence_is_silence() {
        assert_eq!(mix(&[vec![0; FRAME], vec![0; FRAME]]), vec![0; FRAME]);
    }
    #[test]
    fn balanced_mix_preserves_samples() {
        let frame = |n: i16| n.to_le_bytes().repeat(480);
        assert_eq!(mix(&[frame(1000), frame(2000)]), frame(1200));
    }
    #[test]
    fn headroom_is_bounded() {
        let mixed = mix(&[
            i16::MAX.to_le_bytes().repeat(480),
            i16::MAX.to_le_bytes().repeat(480),
        ]);
        assert!(i16::from_le_bytes([mixed[0], mixed[1]]) <= 26214);
    }
}
