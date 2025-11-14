#!/usr/bin/env python3
"""Challenge utilities for MV-CRS (Phase XXX)

Functions provided:
 - atomic_write_json(path, data, retries=3)
 - append_jsonl(path, record)
 - compute_chain_hash(events_path)
 - update_chain_meta(events_path, meta_path)
 - update_summary(events_path, summary_path)
 - write_audit_marker(marker, directory)

All IO operations attempt atomic semantics: write to temp file then rename.
Chain hash is computed deterministically by iteratively hashing canonical JSON lines.
"""

from __future__ import annotations

import json
import os
import time
import uuid
import hashlib
from typing import Any, Dict

def _canonical_json(obj: Dict[str, Any]) -> str:
	return json.dumps(obj, sort_keys=True, separators=(",", ":"))

def atomic_write_json(path: str, data: Dict[str, Any], retries: int = 3, sleep_seconds: float = 0.05) -> None:
	directory = os.path.dirname(path) or "."
	os.makedirs(directory, exist_ok=True)
	tmp_path = f"{path}.tmp-{uuid.uuid4().hex}"
	payload = _canonical_json(data)
	attempt = 0
	while True:
		try:
			with open(tmp_path, "w", encoding="utf-8") as f:
				f.write(payload)
			os.replace(tmp_path, path)
			return
		except OSError:
			attempt += 1
			if attempt >= retries:
				raise
			time.sleep(sleep_seconds)

def append_jsonl(path: str, record: Dict[str, Any]) -> None:
	directory = os.path.dirname(path) or "."
	os.makedirs(directory, exist_ok=True)
	line = _canonical_json(record)
	# Append (not atomic for the single write but acceptable; chain meta updated separately atomically)
	with open(path, "a", encoding="utf-8") as f:
		f.write(line + "\n")

def compute_chain_hash(events_path: str) -> str:
	if not os.path.exists(events_path):
		return ""
	h = hashlib.sha256()
	with open(events_path, "r", encoding="utf-8") as f:
		for raw in f:
			line = raw.strip()
			if not line:
				continue
			# Parse to canonical form to ignore key ordering if any existing lines were not canonical
			try:
				obj = json.loads(line)
			except json.JSONDecodeError:
				obj = {"raw": line}
			canonical = _canonical_json(obj)
			h.update(canonical.encode("utf-8"))
	return h.hexdigest()

def update_chain_meta(events_path: str, meta_path: str) -> Dict[str, Any]:
	chain_hash = compute_chain_hash(events_path)
	count = 0
	if os.path.exists(events_path):
		with open(events_path, "r", encoding="utf-8") as f:
			for line in f:
				if line.strip():
					count += 1
	meta = {
		"last_updated": int(time.time()),
		"count": count,
		"chain_hash": chain_hash,
	}
	atomic_write_json(meta_path, meta)
	return meta

def update_summary(events_path: str, summary_path: str) -> Dict[str, Any]:
	soft = material = critical = 0
	deviations = []
	if os.path.exists(events_path):
		with open(events_path, "r", encoding="utf-8") as f:
			for line in f:
				line = line.strip()
				if not line:
					continue
				try:
					obj = json.loads(line)
				except json.JSONDecodeError:
					continue
				lvl = obj.get("level")
				if lvl == "soft":
					soft += 1
				elif lvl == "material":
					material += 1
				elif lvl == "critical":
					critical += 1
				if "deviation" in obj and isinstance(obj["deviation"], (int, float)):
					deviations.append(float(obj["deviation"]))
	avg_dev = sum(deviations) / len(deviations) if deviations else 0.0
	summary = {
		"last_updated": int(time.time()),
		"daily_challenge_count": soft + material + critical,
		"open_material": material,  # Placeholder: treat all as open until resolution logic exists
		"open_critical": critical,
		"last_level": None,  # Could be set from last event line
		"avg_deviation": round(avg_dev, 6),
	}
	atomic_write_json(summary_path, summary)
	return summary

def write_audit_marker(marker: str, directory: str) -> str:
	os.makedirs(directory, exist_ok=True)
	path = os.path.join(directory, f"audit_{marker}_{int(time.time())}.marker")
	atomic_write_json(path, {"marker": marker, "ts": int(time.time())})
	return path

__all__ = [
	"atomic_write_json",
	"append_jsonl",
	"compute_chain_hash",
	"update_chain_meta",
	"update_summary",
	"write_audit_marker",
]
