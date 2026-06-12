#!/bin/bash
# Macro Recorder - ตัวเปิดสำหรับ Linux
# ติดตั้งครั้งแรก: pip3 install pynput
cd "$(dirname "$0")"
exec python3 MacroRecorder.pyw "$@"
