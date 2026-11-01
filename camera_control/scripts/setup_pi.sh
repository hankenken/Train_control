#!/usr/bin/env bash
# User-invoked setup for Raspberry Pi OS 64-bit on Raspberry Pi 5.
# Installs dependencies only. Does not start services, reboot, or operate GPIO.
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
venv_path="${project_root}/.venv-camera"
check_only=false
while (($#)); do
  case "$1" in
    --check-only) check_only=true; shift ;;
    --venv)
      if (($# < 2)); then printf '%s\n' '--venv requires a path.' >&2; exit 2; fi
      venv_path="$2"; shift 2 ;;
    --help|-h)
      printf '%s\n' 'Usage: bash camera_control/scripts/setup_pi.sh [--check-only] [--venv PATH]' 'Requires Raspberry Pi 5 and Raspberry Pi OS 64-bit (Bookworm or later).'
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done

# All platform checks precede apt, venv creation, and other system changes.
model_path=/proc/device-tree/model
if [[ ! -r "$model_path" ]]; then model_path=/sys/firmware/devicetree/base/model; fi
if [[ ! -r "$model_path" ]]; then printf '%s\n' 'Raspberry Pi model information is unavailable. Nothing was installed.' >&2; exit 1; fi
model="$(tr -d '\000' < "$model_path")"
if [[ "$model" != Raspberry\ Pi\ 5* ]]; then printf 'Unsupported model: %s. Raspberry Pi 5 is required. Nothing was installed.\n' "$model" >&2; exit 1; fi
if [[ "$(uname -m)" != aarch64 || "$(getconf LONG_BIT)" != 64 ]]; then printf '%s\n' 'Raspberry Pi OS 64-bit is required. Nothing was installed.' >&2; exit 1; fi
if [[ ! -r /etc/os-release || ! -r /etc/rpi-issue ]]; then printf '%s\n' 'Raspberry Pi OS could not be confirmed (/etc/rpi-issue). Nothing was installed.' >&2; exit 1; fi
# /etc/os-release is a local OS-owned configuration file.
. /etc/os-release
if [[ "${ID:-}" != debian && "${ID:-}" != raspbian ]]; then printf 'Unsupported OS: %s. Nothing was installed.\n' "${PRETTY_NAME:-unknown}" >&2; exit 1; fi
case "${VERSION_CODENAME:-}" in
  bookworm|trixie) ;;
  *) printf 'Use Raspberry Pi OS 64-bit Bookworm or Trixie; detected: %s. Nothing was installed.\n' "${PRETTY_NAME:-unknown}" >&2; exit 1 ;;
esac
printf 'Platform: %s / %s / 64-bit\n' "$model" "${PRETTY_NAME:-Raspberry Pi OS}"
if "$check_only"; then printf '%s\n' 'Platform checks passed. No packages were installed.'; exit 0; fi
if [[ "$(id -u)" == 0 ]]; then
  apt_runner=()
else
  if ! command -v sudo >/dev/null; then printf '%s\n' 'sudo is required for apt installation.' >&2; exit 1; fi
  apt_runner=(sudo)
fi
"${apt_runner[@]}" apt-get update
"${apt_runner[@]}" apt-get install -y --no-install-recommends python3-picamera2 python3-opencv python3-numpy python3-venv rpicam-apps
python3 -m venv --system-site-packages "$venv_path"
"${venv_path}/bin/python" -m pip install -r "${project_root}/camera_control/requirements.txt"
"${venv_path}/bin/python" -c 'import cv2, numpy; from picamera2 import Picamera2; import fastapi, uvicorn; print("Dependencies available; no camera stream or GPIO output was started.")'
printf '\nSetup complete. No service was enabled and no reboot was requested.\n'
printf 'Next: %q %q\n' "${venv_path}/bin/python" "${project_root}/camera_control/scripts/check_cameras.py"
