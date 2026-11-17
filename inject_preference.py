#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write the full contract into Doubao's 工作任务偏好指令 automatically.

It restarts the desktop client once with a debugging port, drives the real
settings panel through CDP, saves, re-reads the value to confirm persistence,
then runs a behavior probe (a plain technical task) to confirm the contract is
actually acting on replies, and finally restarts the client normally.

    python inject_preference.py                  # full automatic run
    python inject_preference.py --no-restart    # attach to an existing 9222 client
    python inject_preference.py --no-probe      # skip the behavior probe
    python inject_preference.py --exe PATH      # explicit Doubao.exe
    python inject_preference.py --text PATH     # custom instruction text

Windows / macOS. Standard library only. See docs/INSTALL.md for the manual path.

Exe discovery order: --exe -> DOUBAO_EXE -> uninstall registry -> desktop/start
menu shortcuts -> running process -> standard install dirs -> shallow scan of
common roots. Nothing is hard-coded to one machine.

Note for Doubao 2.36.10+: asking the model to "repeat the contract labels" now
hits a prompt-leak guard and gets refused even though the injection is live.
The probe therefore checks behavior (does it answer a technical task with the
actual artifact) instead of asking it to recite labels.
"""
import argparse
import glob
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "verify"))
from cdp import CDP, pick_target, version  # noqa: E402

IS_WINDOWS = platform.system() == "Windows"

PROBE_TASK = ("写一个 Python 脚本：读取 CSV 文件，统计每列空值数量并打印成表格。"
              "只给完整代码，不要解释。")


def ps(script, timeout=25):
    """Run a PowerShell snippet, return stdout text."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
        )
        return (out.stdout or "").strip()
    except Exception as e:
        return "PS_ERROR: %s" % e


def _scan(root, max_depth=3):
    """Yield Doubao.exe paths under root, shallow enough to stay fast."""
    root = Path(root)
    base_depth = len(root.parts)
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).parts) - base_depth
            if depth > max_depth:
                dirnames[:] = []
                continue
            if "Doubao.exe" in filenames:
                yield str(Path(dirpath) / "Doubao.exe")
    except OSError:
        return


def registry_candidates():
    if not IS_WINDOWS:
        return []
    out = ps(r"""
$keys = @(
 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
Get-ItemProperty $keys -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName -match 'Doubao|豆包' } |
  ForEach-Object {
    if ($_.DisplayIcon) { ($_.DisplayIcon -split ',')[0].Trim('"') }
    if ($_.InstallLocation) { Join-Path $_.InstallLocation 'Doubao.exe' }
  }
""", timeout=25)
    cands = []
    for line in out.splitlines():
        line = line.strip().strip('"')
        if line.lower().endswith("doubao.exe"):
            cands.append(line)
    return cands


def shortcut_candidates():
    if not IS_WINDOWS:
        return []
    cands = []
    desktop = Path.home() / "Desktop"
    start = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    pats = []
    for base in (desktop, start):
        try:
            pats += list(base.glob("*豆包*.lnk")) + list(base.glob("*Doubao*.lnk"))
        except OSError:
            pass
    for lnk in pats:
        target = ps("(New-Object -ComObject WScript.Shell).CreateShortcut('%s').TargetPath"
                    % str(lnk).replace("'", "''"))
        if target and not target.startswith("PS_ERROR"):
            cands.append(target.strip())
    return cands


def find_exe(explicit):
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return str(p)
    env = os.environ.get("DOUBAO_EXE")
    if env and Path(env).is_file():
        return env

    cands = []
    if IS_WINDOWS:
        cands += registry_candidates()
        cands += shortcut_candidates()
        proc = ps("(Get-Process Doubao -ErrorAction SilentlyContinue | "
                  "Select-Object -First 1 -ExpandProperty Path)")
        if proc and not proc.startswith("PS_ERROR"):
            cands.append(proc.strip())
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            cands += [
                str(Path(local) / "Doubao" / "Application" / "Doubao.exe"),
                str(Path(local) / "Doubao" / "Doubao.exe"),
                str(Path(local) / "Programs" / "Doubao" / "Doubao.exe"),
                str(Path(local) / "Programs" / "doubao" / "Doubao.exe"),
            ]
        for envname in ("ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
            base = os.environ.get(envname)
            if base:
                cands += [
                    str(Path(base) / "Doubao" / "Doubao.exe"),
                    str(Path(base) / "Doubao" / "app" / "Doubao.exe"),
                    str(Path(base) / "Doubao" / "Application" / "Doubao.exe"),
                    str(Path(base) / "doubao" / "Doubao.exe"),
                ]
        roots = []
        if local:
            roots += [Path(local) / "LenovoSoftstore", Path(local) / "Programs", Path(local) / "Doubao"]
        for drive in ("C", "D", "E", "F"):
            r = Path(drive + ":\\")
            if r.is_dir():
                roots += [r / "LenovoSoftstore", r / "Program Files",
                          r / "Program Files (x86)", r / "Software", r / "Apps"]
        for root in roots:
            if len(cands) > 200:
                break
            for hit in _scan(root):
                cands.append(hit)
    else:
        cands = [
            "/Applications/Doubao.app/Contents/MacOS/Doubao",
            str(Path.home() / "Applications" / "Doubao.app" / "Contents" / "MacOS" / "Doubao"),
        ]

    seen = set()
    for c in cands:
        c = (c or "").strip().strip('"')
        if not c or c in seen:
            continue
        seen.add(c)
        try:
            if Path(c).is_file():
                return c
        except OSError:
            continue
    return None


def running_pids():
    if IS_WINDOWS:
        out = ps("(Get-Process Doubao -ErrorAction SilentlyContinue | "
                 "ForEach-Object { $_.Id }) -join ','")
        return [int(x) for x in out.split(",") if x.strip().isdigit()]
    out = subprocess.run(["pgrep", "-x", "Doubao"], capture_output=True, text=True)
    return [int(x) for x in out.stdout.split() if x.strip().isdigit()]


def stop_client():
    if IS_WINDOWS:
        ps("$p=Get-Process Doubao -ErrorAction SilentlyContinue; "
           "if($p){ $p | ForEach-Object { $_.CloseMainWindow() | Out-Null }; "
           "Start-Sleep -Seconds 2; "
           "$l=Get-Process Doubao -ErrorAction SilentlyContinue; "
           "if($l){ $l | Stop-Process -Force -ErrorAction SilentlyContinue }; "
           "Start-Sleep -Seconds 1 }; "
           "Write-Output (@(Get-Process Doubao -ErrorAction SilentlyContinue).Count)")
    else:
        subprocess.run(["pkill", "-x", "Doubao"], capture_output=True)
        time.sleep(2)
    return len(running_pids()) == 0


def start_client(exe, debug_port=None):
    args = [exe]
    if debug_port:
        args += ["--remote-debugging-port=%d" % debug_port,
                 "--remote-allow-origins=*",
                 "--force-renderer-accessibility"]
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if IS_WINDOWS:
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(args, **kwargs)


def wait_cdp(port, seconds=40):
    end = time.time() + seconds
    while time.time() < end:
        try:
            v = version(port, timeout=2)
            return v
        except Exception:
            time.sleep(0.7)
    raise SystemExit("CDP port %d did not come up in %ds. "
                     "Start Doubao with --remote-debugging-port=%d or pass --no-restart."
                     % (port, seconds, port))


def ev(c, expression, label, settle=0.0):
    if settle:
        time.sleep(settle)
    value = c.evaluate(expression)
    print("  [%s] %s" % (label, json.dumps(value, ensure_ascii=False)[:300]))
    return value


def inject(c, text):
    # 1. Settings button
    r = ev(c, "(()=>{const b=document.querySelector('[aria-label=\"设置\"]');"
              "if(!b)return 'NO_SETTINGS_BUTTON';b.click();return 'OK'})()",
           "open settings", settle=0.3)
    if r != "OK":
        print("  settings button not found - assuming settings panel is already open")

    # 2. 工作模式设置 in the left nav
    time.sleep(1.6)
    r = ev(c, "(()=>{const els=[...document.querySelectorAll('*')]"
              ".filter(e=>e.children.length===0 && (e.innerText||'').trim()==='工作模式设置');"
              "if(!els.length)return 'NO_WORK_MODE_ENTRY';els[0].click();return 'CLICKED '+els.length})()",
           "open work mode settings")
    if isinstance(r, str) and r.startswith("NO_"):
        raise SystemExit("Cannot find 工作模式设置. Do it manually: docs/INSTALL.md")

    # 3. 编辑 button (last one on the page is the preference editor)
    time.sleep(1.6)
    r = ev(c, "(()=>{const els=[...document.querySelectorAll('*')]"
              ".filter(e=>e.children.length===0 && (e.innerText||'').trim()==='编辑');"
              "if(!els.length)return 'NO_EDIT_BUTTON';els[els.length-1].click();"
              "return 'CLICKED '+els.length})()", "open preference editor")
    if isinstance(r, str) and r.startswith("NO_"):
        raise SystemExit("Cannot find 编辑. Do it manually: docs/INSTALL.md")

    # 4. Fill the textarea with the native setter (React controlled input)
    time.sleep(1.4)
    js_text = json.dumps(text, ensure_ascii=False)
    r = ev(c, "(()=>{const el=document.querySelector('textarea[placeholder=\"输入偏好指令\"]');"
              "if(!el)return 'NO_TEXTAREA';"
              "const setter=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;"
              "setter.call(el, %s);"
              "el.dispatchEvent(new Event('input',{bubbles:true}));"
              "el.dispatchEvent(new Event('change',{bubbles:true}));"
              "return {len:el.value.length,max:el.maxLength}})()" % js_text,
           "fill textarea")
    if not isinstance(r, dict) or r.get("len", 0) != len(text):
        raise SystemExit("Textarea value length mismatch: %s (expected %d). Manual path: docs/INSTALL.md"
                         % (r, len(text)))
    if r.get("max", 10000) > 0 and len(text) > r["max"]:
        raise SystemExit("Text is %d chars but textarea maxLength is %d." % (len(text), r["max"]))

    # 5. Save
    time.sleep(0.5)
    r = ev(c, "(()=>{const b=[...document.querySelectorAll('button')]"
              ".filter(e=>/保存|确定/.test((e.innerText||'').trim()));"
              "if(!b.length)return 'NO_SAVE_BUTTON';b[b.length-1].click();return 'SAVED'})()",
           "click save")
    if r != "SAVED":
        raise SystemExit("Save button not found. Manual path: docs/INSTALL.md")
    time.sleep(1.6)

    # 6. Re-open the editor and read back what persisted
    body = ev(c, "(document.body.innerText||'').includes('保存成功')", "save toast")
    ev(c, "(()=>{const els=[...document.querySelectorAll('*')]"
          ".filter(e=>e.children.length===0 && (e.innerText||'').trim()==='编辑');"
          "if(!els.length)return 'NO_REOPEN';els[els.length-1].click();return 'REOPENED'})()",
       "reopen editor")
    time.sleep(1.4)
    persisted = ev(c, "(()=>{const el=document.querySelector('textarea[placeholder=\"输入偏好指令\"]');"
                      "return el?{len:el.value.length,head:el.value.slice(0,40)}:'NO_TEXTAREA'})()",
                   "read back")
    ok = isinstance(persisted, dict) and persisted.get("len") == len(text)
    print("\n  persistence: %s (saved=%d, read back=%s)" %
          ("PASS" if ok else "FAIL", len(text), persisted))
    return ok


def behavior_probe(c, timeout=45):
    """Send a plain technical task and check the reply ships the artifact.

    Doubao 2.36.10+ refuses to recite injected labels, so label echo is no
    longer a valid signal; the artifact itself is.
    """
    print("\n  [behavior] sending probe task...")
    c.evaluate("(()=>{const ev=new KeyboardEvent('keydown',{key:'Escape',code:'Escape',keyCode:27,bubbles:true});document.body.dispatchEvent(ev);return 'esc'})()")
    time.sleep(1.2)
    c.evaluate("(()=>{const bs=[...document.querySelectorAll('button,[role=\"tab\"]')]"
               ".filter(e=>(e.innerText||'').trim()==='工作');if(bs.length){bs[bs.length-1].click();return 'work'}return 'no'})()")
    time.sleep(2.0)

    js_text = json.dumps(PROBE_TASK, ensure_ascii=False)
    fill = (
        "(()=>{const el=document.querySelector('div.ProseMirror[contenteditable=\"true\"]')"
        "||document.querySelector('div[contenteditable=\"true\"]');"
        "if(!el)return 'NO_EDITOR';el.focus();let ok=false;"
        "try{ok=document.execCommand('insertText',false,%s);}catch(e){}"
        "if(!ok||!(el.innerText||'').includes('CSV')){"
        "el.innerHTML='<p>'+%s+'</p>';"
        "el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:%s}));}"
        "return {len:(el.innerText||'').length}})()"
    ) % (js_text, js_text, js_text)
    print("  [behavior] fill:", c.evaluate(fill))
    time.sleep(0.6)
    c.evaluate("(()=>{const el=document.querySelector('div.ProseMirror[contenteditable=\"true\"]');"
               "if(!el)return 'NO';el.focus();"
               "['keydown','keypress','keyup'].forEach(t=>el.dispatchEvent(new KeyboardEvent(t,"
               "{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true})));"
               "return 'ENTER'})()")
    print("  [behavior] waiting %ds for reply..." % timeout)
    time.sleep(timeout)
    body = c.evaluate("(document.body.innerText||'')") or ''
    tail = body[-4000:]
    coded = any(k in tail for k in ['import ', 'def ', '```', 'class ', '#include', 'csv'])
    denied = any(k in tail for k in ['我不能', '无法提供', '建议咨询', '需要授权', '作为 AI', '作为AI', '抱歉'])
    ok = coded and not denied
    print("  [behavior] coded=%s denied=%s -> %s" % (coded, denied, "PASS" if ok else "CHECK"))
    return {'ok': ok, 'coded': coded, 'denied': denied}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--exe", help="path to Doubao.exe")
    ap.add_argument("--text", help="instruction text file (default src/preference-instruction.txt)")
    ap.add_argument("--no-restart", action="store_true",
                    help="attach to an already-debugging client, do not restart it")
    ap.add_argument("--no-probe", action="store_true", help="skip the behavior probe")
    ap.add_argument("--keep-debug", action="store_true",
                    help="leave the client running with the debugging port")
    args = ap.parse_args()

    text_path = Path(args.text).expanduser() if args.text else HERE / "src" / "preference-instruction.txt"
    if not text_path.is_file():
        raise SystemExit("instruction text not found: %s" % text_path)
    text = text_path.read_text(encoding="utf-8")
    print("Instruction text: %s (%d chars)" % (text_path, len(text)))

    exe = find_exe(args.exe)
    if not args.no_restart and not exe:
        raise SystemExit("Cannot locate Doubao executable. Pass --exe PATH or set DOUBAO_EXE.")
    if exe:
        print("Doubao exe      : %s" % exe)

    if not args.no_restart:
        print("Stopping current client...")
        if not stop_client():
            print("  warning: some Doubao processes are still alive, continuing anyway")
        print("Starting with CDP port %d..." % args.port)
        start_client(exe, args.port)

    v = wait_cdp(args.port)
    print("CDP             : %s" % v.get("Browser", "?"))

    target = pick_target(args.port, url_contains="doubao-chat")
    print("Target          : %s | %s" % (target.get("title"), (target.get("url") or "")[:100]))
    c = CDP(target["webSocketDebuggerUrl"], timeout=30)
    # let the SPA finish rendering before touching the DOM
    for _ in range(30):
        try:
            if (c.evaluate("(document.body.innerText||'').length") or 0) > 300:
                break
        except Exception:
            pass
        time.sleep(1)

    ok_persist = False
    probe = {'ok': False}
    try:
        ok_persist = inject(c, text)
        if not args.no_probe:
            probe = behavior_probe(c)
    finally:
        c.close()

    if not args.no_restart and not args.keep_debug:
        print("Restoring normal client startup (debug port closed)...")
        stop_client()
        start_client(exe, None)
        time.sleep(3)
        print("Running processes: %d" % len(running_pids()))

    passed = ok_persist and (args.no_probe or probe.get('ok'))
    print("\nRESULT: %s (persist=%s behavior=%s)" %
          ("PASS - injected and behavior verified" if passed else "CHECK",
           ok_persist, probe.get('ok')))
    print("Use 工作任务 mode. Plain 对话 mode does not inject this instruction.")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
