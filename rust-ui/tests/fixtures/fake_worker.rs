use std::io::{self, BufRead, Write};
use std::thread;
use std::time::Duration;

use serde_json::{Value, json};

fn emit(job_id: &str, event: &str, payload: Value) {
    let mut record = json!({"v": 1, "job_id": job_id, "event": event});
    if let (Some(destination), Some(fields)) = (record.as_object_mut(), payload.as_object()) {
        destination.extend(fields.clone());
    }
    println!("{}", record);
    io::stdout().flush().expect("flush worker event");
}

fn main() {
    let stdin = io::stdin();
    let mut lines = stdin.lock().lines();
    let start = lines
        .next()
        .expect("start command")
        .expect("read start command");
    let start: Value = serde_json::from_str(&start).expect("parse start command");
    let job_id = start["job_id"].as_str().expect("job id").to_owned();
    let options = &start["options"];

    match options["fake_mode"].as_str().unwrap_or("success") {
        "delayed" => {
            emit(&job_id, "started", json!({}));
            thread::sleep(Duration::from_millis(350));
            emit(&job_id, "completed", json!({"outcome": "success"}));
        }
        "no-results" => emit(&job_id, "completed", json!({"outcome": "no-results"})),
        "wrong-version" => {
            println!("{}", json!({"v": 2, "job_id": job_id, "event": "started"}));
            io::stdout().flush().expect("flush invalid event");
        }
        "wrong-job-id" => {
            println!(
                "{}",
                json!({"v": 1, "job_id": "another-job", "event": "started"})
            );
            io::stdout().flush().expect("flush invalid event");
        }
        "crash" => {
            emit(&job_id, "started", json!({}));
            std::process::exit(7);
        }
        "completed-nonzero" => {
            emit(&job_id, "completed", json!({"outcome": "success"}));
            std::process::exit(7);
        }
        "completed-delayed-close" => {
            emit(&job_id, "completed", json!({"outcome":"success"}));
            thread::sleep(Duration::from_millis(300));
        }
        "completed-trailing-invalid" => {
            emit(&job_id, "completed", json!({"outcome": "success"}));
            thread::sleep(Duration::from_millis(75));
            println!("not a JSON-lines protocol record");
            io::stdout().flush().expect("flush trailing invalid record");
        }
        "cancel" => {
            emit(&job_id, "started", json!({}));
            let cancel = lines
                .next()
                .expect("cancel command")
                .expect("read cancel command");
            let cancel: Value = serde_json::from_str(&cancel).expect("parse cancel command");
            if cancel == json!({"v": 1, "job_id": job_id, "command": "cancel"}) {
                emit(&job_id, "completed", json!({"outcome": "cancelled"}));
            } else {
                emit(
                    &job_id,
                    "error",
                    json!({"message": "unexpected cancel record"}),
                );
                emit(&job_id, "completed", json!({"outcome": "failed"}));
            }
        }
        "cookie" => {
            let input_includes_cookie_value = start.to_string().contains("COOKIE_SENTINEL_SECRET");
            emit(
                &job_id,
                "completed",
                json!({"outcome": "success", "summary": {"cookie_value_forwarded": input_includes_cookie_value}}),
            );
        }
        _ => emit(&job_id, "completed", json!({"outcome": "success"})),
    }
}
