"""Verify diagnostic-stream full echo and ECHO-ACK v1 without radio hardware."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "contracts/i1v2_ref"))
import i1_ble_binding as ble
import i1v2_reference as i1

VECTORS_SHA = "6aaaed46c5caf217330837bbc27ae75b4f61dfe4d13e6d9cf874fcafde73c950"
SV1_SIZES = (64, 104, 112, 128, 130, 233, 256, 436, 512, 1024, 2048, 4096)


def reply(frame):
    header = i1.parse_envelope(frame, max(SV1_SIZES))
    if (header.version, header.message_type, header.header_length,
            header.metadata_length, header.nonce_length) != (2, 1, 32, 0, 0):
        raise i1.Drop("ECHO_HEADER")
    if header.reserved_0 == 0:
        return header.request_id, "full", frame
    if header.reserved_0 == 1:
        payload = struct.pack("<I", len(frame)) + hashlib.sha256(frame).digest()
        return header.request_id, "ack", i1.frame(2, 0, header.request_id, b"", b"", payload)
    raise i1.Drop("ECHO_MODE")


def through_binding(frame, transfer_id, mtu):
    reassembler = ble.Reassembler(streams=frozenset({ble.STREAM_DIAG_ECHO}))
    stream, received = None, None
    for fragment in ble.fragment(frame, ble.STREAM_DIAG_ECHO, transfer_id, mtu):
        result = reassembler.feed(fragment, 0)
        if result is not None:
            stream, received = result
    if (stream, received) != (ble.STREAM_DIAG_ECHO, frame):
        raise ValueError("BLE reassembly differs from input")
    return received


def check_vectors(vectors_path, output):
    vectors_bytes = vectors_path.read_bytes()
    if hashlib.sha256(vectors_bytes).hexdigest() != VECTORS_SHA:
        raise ValueError("SHA-256 differs from SV1 vector set dated 26/11")
    data = json.loads(vectors_bytes)
    vectors = data["vectors"]
    coverage = {(row["length"], row["mode"]) for row in vectors}
    expected = {(size, mode) for size in SV1_SIZES for mode in ("full", "ack")}
    if data["schema"] != "week11-echo-vectors/2" or len(vectors) != 24 or coverage != expected:
        raise ValueError("Unexpected SV1 vector schema or coverage")

    supplemental = []
    for reserved, mode in enumerate(("full", "ack")):
        request_id = 0x01020304
        payload = bytes(index % 256 for index in range(362 - i1.FIXED_HEADER - i1.CRC_BYTES))
        frame = i1.frame(1, 0, request_id, b"", b"", payload, reserved_0=reserved)
        # Expected ACK uses the wire offsets and CRC independently of reply().
        header = struct.pack("<4sBBHHHIIIIHH", b"I1PK", 2, 2, 0, 32, 0,
                             72, request_id, 0, 36, 0, 0)
        body = header + struct.pack("<I", 362) + hashlib.sha256(frame).digest()
        answer = frame if mode == "full" else body + struct.pack("<I", i1.crc32(body))
        supplemental.append(dict(length=362, request_id=request_id, mode=mode, frame_hex=frame.hex(),
                                 frame_sha256=hashlib.sha256(frame).hexdigest(), answer_hex=answer.hex()))

    rows = []
    for source, cases in (("sv1", vectors), ("supplemental", supplemental)):
        for vector in cases:
            frame = bytes.fromhex(vector["frame_hex"])
            if len(frame) != vector["length"] or hashlib.sha256(frame).hexdigest() != vector["frame_sha256"]:
                raise ValueError("Invalid input bytes for echo vector")
            for mtu in (23, 247):
                request_id, mode, answer = reply(through_binding(frame, 1, mtu))
                if ((request_id, mode) != (vector["request_id"], vector["mode"])
                        or through_binding(answer, 2, mtu).hex() != vector["answer_hex"]):
                    raise ValueError(f"Response differs: {source}, {len(frame)} B, {mode}, MTU={mtu}")
                rows.append(dict(source=source, input_bytes=len(frame), mode=mode, mtu=mtu,
                                 response_bytes=len(answer), request_id=request_id,
                                 frame_sha256=vector["frame_sha256"],
                                 response_sha256=hashlib.sha256(answer).hexdigest()))
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, output / "echo_host.py")
    (output / "echo_vectors.json").write_bytes(vectors_bytes)
    (output / "supplemental_362.json").write_text(json.dumps(supplemental, indent=2) + "\n")
    with (output / "echo_checks.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    inventory = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                 (Path(i1.__file__), Path(ble.__file__))}
    summary = dict(status="HOST_ECHO_OK", scope="HOST_I1_BLE_BINDING", sv1_vectors=len(vectors),
                   supplemental_vectors=len(supplemental), binding_checks=len(rows), mtu=[23, 247],
                   sizes_bytes=sorted(set(SV1_SIZES) | {362}), sv1_vectors_sha256=VECTORS_SHA,
                   binding_source_sha256=inventory)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (output / "sha256sum_results.txt").open("x") as stream:
        for path in sorted(output.glob("*")):
            if path.name != "sha256sum_results.txt":
                stream.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    print(f"HOST_ECHO_OK {len(vectors)}/24 + {len(supplemental)}/2, binding_checks={len(rows)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check_vectors(args.vectors, args.output)
