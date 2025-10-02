from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
from pydantic import ValidationError
from models import SurveySubmission, StoredSurveyRecord
from storage import append_json_line

import hashlib  # <-- added this

def _sha256_hex(s: str) -> str:  # <-- and this helper right under it
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

app = Flask(__name__)
# Allow cross-origin requests so the static HTML can POST from localhost or file://
CORS(app, resources={r"/v1/*": {"origins": "*"}})

@app.route("/ping", methods=["GET"])
def ping():
    """Simple health check endpoint."""
    return jsonify({
        "status": "ok",
        "message": "API is alive",
        "utc_time": datetime.now(timezone.utc).isoformat()
    })

@app.post("/v1/survey")
def submit_survey():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "invalid_json", "detail": "Body must be application/json"}), 400

    try:
        submission = SurveySubmission(**payload)
    except ValidationError as ve:
        return jsonify({"error": "validation_error", "detail": ve.errors()}), 422

    # Hash PII
    email_norm = submission.email.strip().lower()
    email_hash = _sha256_hex(email_norm)
    age_hash   = _sha256_hex(str(submission.age))

    # submission_id: client-provided or server-generated (email + UTC YYYYMMDDHH)
    if submission.submission_id:
        submission_id = submission.submission_id
    else:
        hour_stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        submission_id = _sha256_hex(f"{email_norm}|{hour_stamp}")

    # user_agent: prefer payload, fall back to request header
    ua = submission.user_agent or request.headers.get("User-Agent", "")

    # Build stored record WITHOUT raw email/age
    base = submission.dict(exclude={"email", "age", "submission_id", "user_agent"})
    record = StoredSurveyRecord(
        **base,
        email_hash=email_hash,
        age_hash=age_hash,
        submission_id=submission_id,
        user_agent=ua,
        received_at=datetime.now(timezone.utc),
        ip=request.headers.get("X-Forwarded-For", request.remote_addr or "")
    )

    append_json_line(record.dict())
    return jsonify({"status": "ok", "submission_id": submission_id}), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)