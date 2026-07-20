//! Custom `watcher://` URI scheme — serves live-preview JPEGs and clip video
//! files directly to `<img>`/`<video>` elements without going through the
//! JSON invoke channel (TD-5: preview must never ride JSON invoke; TD-1: HEVC
//! playback needs Range support for WebView2 seeking).
//!
//! Routes:
//!   GET /preview/m{index}         → {segments_dir}/m{index}/preview.jpg
//!   GET /clip/{base64url(path)}   → the clip file, with HTTP Range support
//!
//! Every resolved path is canonicalized and checked against the allowlist in
//! `MediaRoots` (populated from the backend's `get_media_roots` command right
//! after the pipe connects) before it is served — a client cannot escape the
//! segments/clips/storage directories.

use std::path::{Path, PathBuf};
use std::sync::Arc;

use base64::Engine;
use tauri::http::{self, Request, Response, StatusCode};
use tauri::UriSchemeContext;
use tokio::io::{AsyncReadExt, AsyncSeekExt};
use tokio::sync::RwLock;

pub const SCHEME: &str = "watcher";

#[derive(Clone, Default)]
pub struct MediaRootsState(pub Arc<RwLock<Option<MediaRoots>>>);

#[derive(Clone, Debug)]
pub struct MediaRoots {
    pub segments_dir: PathBuf,
    pub clips_dir: PathBuf,
    pub storage_roots: Vec<PathBuf>,
}

impl MediaRoots {
    pub fn from_json(v: &serde_json::Value) -> Option<Self> {
        let segments_dir = v.get("segments_dir")?.as_str()?.into();
        let clips_dir = v.get("clips_dir")?.as_str()?.into();
        let storage_roots = v
            .get("storage_roots")
            .and_then(|s| s.as_array())
            .map(|arr| arr.iter().filter_map(|x| x.as_str()).map(PathBuf::from).collect())
            .unwrap_or_default();
        Some(Self { segments_dir, clips_dir, storage_roots })
    }

    /// True if `path` canonicalizes to somewhere under one of the allowed roots.
    fn allows(&self, path: &Path) -> bool {
        let Ok(canon) = path.canonicalize() else { return false };
        [&self.segments_dir, &self.clips_dir]
            .into_iter()
            .chain(self.storage_roots.iter())
            .filter_map(|root| root.canonicalize().ok())
            .any(|root| canon.starts_with(root))
    }
}

fn empty_response(status: StatusCode) -> Response<Vec<u8>> {
    Response::builder().status(status).body(Vec::new()).unwrap()
}

fn content_type_for(path: &Path) -> &'static str {
    match path.extension().and_then(|e| e.to_str()).unwrap_or("").to_lowercase().as_str() {
        "jpg" | "jpeg" => "image/jpeg",
        "mp4" | "m4v" => "video/mp4",
        "ts" => "video/mp2t",
        _ => "application/octet-stream",
    }
}

/// Register the `watcher://` protocol on the Tauri builder.
pub fn register<R: tauri::Runtime>(
    builder: tauri::Builder<R>,
    roots: MediaRootsState,
) -> tauri::Builder<R> {
    builder.register_asynchronous_uri_scheme_protocol(SCHEME, move |_ctx: UriSchemeContext<R>, request, responder| {
        let roots = roots.clone();
        tauri::async_runtime::spawn(async move {
            let response = handle(&roots, request).await;
            responder.respond(response);
        });
    })
}

async fn handle(roots: &MediaRootsState, request: Request<Vec<u8>>) -> Response<Vec<u8>> {
    let guard = roots.0.read().await;
    let Some(roots) = guard.as_ref() else {
        return empty_response(StatusCode::SERVICE_UNAVAILABLE);
    };

    let path_and_query = request.uri().path();
    let segments: Vec<&str> = path_and_query.trim_start_matches('/').splitn(2, '/').collect();

    let target: PathBuf = match segments.as_slice() {
        ["preview", rest] => {
            // rest = "m{index}"
            roots.segments_dir.join(rest).join("preview.jpg")
        }
        ["clip", encoded] => {
            let Ok(decoded) = base64::engine::general_purpose::URL_SAFE_NO_PAD.decode(encoded) else {
                return empty_response(StatusCode::BAD_REQUEST);
            };
            let Ok(decoded_str) = String::from_utf8(decoded) else {
                return empty_response(StatusCode::BAD_REQUEST);
            };
            PathBuf::from(decoded_str)
        }
        _ => return empty_response(StatusCode::NOT_FOUND),
    };

    if !roots.allows(&target) {
        return empty_response(StatusCode::FORBIDDEN);
    }

    serve_file(&target, request).await
}

async fn serve_file(path: &Path, request: Request<Vec<u8>>) -> Response<Vec<u8>> {
    let Ok(mut file) = tokio::fs::File::open(path).await else {
        return empty_response(StatusCode::NOT_FOUND);
    };
    let Ok(metadata) = file.metadata().await else {
        return empty_response(StatusCode::NOT_FOUND);
    };
    let file_len = metadata.len();
    let content_type = content_type_for(path);

    let range_header = request
        .headers()
        .get(http::header::RANGE)
        .and_then(|v| v.to_str().ok())
        .map(str::to_owned);

    // Previews are tiny and change every ~500ms — never cache them.
    let cache_control = if path.extension().and_then(|e| e.to_str()) == Some("jpg") {
        "no-store"
    } else {
        "no-cache"
    };

    match range_header.and_then(|h| parse_range(&h, file_len)) {
        Some((start, end)) if start <= end && end < file_len => {
            let len = end - start + 1;
            if file.seek(std::io::SeekFrom::Start(start)).await.is_err() {
                return empty_response(StatusCode::INTERNAL_SERVER_ERROR);
            }
            let mut buf = vec![0u8; len as usize];
            if file.read_exact(&mut buf).await.is_err() {
                return empty_response(StatusCode::INTERNAL_SERVER_ERROR);
            }
            Response::builder()
                .status(StatusCode::PARTIAL_CONTENT)
                .header(http::header::CONTENT_TYPE, content_type)
                .header(http::header::CONTENT_LENGTH, len)
                .header(http::header::CONTENT_RANGE, format!("bytes {start}-{end}/{file_len}"))
                .header(http::header::ACCEPT_RANGES, "bytes")
                .header(http::header::CACHE_CONTROL, cache_control)
                .body(buf)
                .unwrap()
        }
        Some(_) => empty_response(StatusCode::RANGE_NOT_SATISFIABLE),
        None => {
            let mut buf = Vec::with_capacity(file_len as usize);
            if file.read_to_end(&mut buf).await.is_err() {
                return empty_response(StatusCode::INTERNAL_SERVER_ERROR);
            }
            Response::builder()
                .status(StatusCode::OK)
                .header(http::header::CONTENT_TYPE, content_type)
                .header(http::header::CONTENT_LENGTH, file_len)
                .header(http::header::ACCEPT_RANGES, "bytes")
                .header(http::header::CACHE_CONTROL, cache_control)
                .body(buf)
                .unwrap()
        }
    }
}

/// Parse a single-range `Range: bytes=start-end` header. `end` defaults to
/// `file_len - 1` when omitted (open-ended range).
fn parse_range(header: &str, file_len: u64) -> Option<(u64, u64)> {
    let spec = header.strip_prefix("bytes=")?;
    let (start_s, end_s) = spec.split_once('-')?;
    let start: u64 = start_s.parse().ok()?;
    let end: u64 = if end_s.is_empty() {
        file_len.saturating_sub(1)
    } else {
        end_s.parse().ok()?
    };
    Some((start, end))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_bounded_range() {
        assert_eq!(parse_range("bytes=0-99", 1000), Some((0, 99)));
    }

    #[test]
    fn parses_open_ended_range() {
        assert_eq!(parse_range("bytes=500-", 1000), Some((500, 999)));
    }

    #[test]
    fn rejects_malformed_range() {
        assert_eq!(parse_range("nonsense", 1000), None);
        assert_eq!(parse_range("bytes=abc-99", 1000), None);
    }

    #[test]
    fn allows_rejects_path_outside_roots() {
        let roots = MediaRoots {
            segments_dir: std::env::temp_dir().join("watcher_test_segments"),
            clips_dir: std::env::temp_dir().join("watcher_test_clips"),
            storage_roots: vec![],
        };
        std::fs::create_dir_all(&roots.segments_dir).unwrap();
        let outside = std::env::temp_dir().join("watcher_test_outside_should_not_exist.txt");
        assert!(!roots.allows(&outside));
    }

    #[test]
    fn allows_accepts_path_inside_segments_root() {
        let dir = std::env::temp_dir().join("watcher_test_segments_ok");
        std::fs::create_dir_all(&dir).unwrap();
        let file = dir.join("preview.jpg");
        std::fs::write(&file, b"x").unwrap();
        let roots = MediaRoots {
            segments_dir: dir.clone(),
            clips_dir: std::env::temp_dir().join("watcher_test_clips_ok"),
            storage_roots: vec![],
        };
        assert!(roots.allows(&file));
    }
}
