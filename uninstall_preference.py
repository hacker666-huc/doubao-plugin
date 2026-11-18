#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Clear Doubao's 工作任务偏好指令 automatically (the account-level half of uninstall).

The file half is handled by: python install.py --uninstall

    python uninstall_preference.py               # full automatic run
    python uninstall_preference.py --no-restart  # attach to an existing 9222 client
    python uninstall_preference.py --exe PATH    # explicit Doubao.exe
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "verify"))
sys.path.insert(0, str(HERE))
from cdp import CDP, pick_target, version  # noqa: E402
from inject_preference import find_exe, start_client, stop_client, wait_cdp, running_pids  # noqa: E402


def ev(c, expr, label, settle=0.0):
    if settle:
        time.sleep(settle)
    v = c.evaluate(expr)
    print("  [%s] %s" % (label, json.dumps(v, ensure_ascii=False)[:200]))
    return v


def clear_pref(c):
    ev(c, "(()=>{const b=document.querySelector('[aria-label=\"设置\"]');if(!b)return 'NO';b.click();return 'OK'})()",
       'open settings', 0.4)
    time.sleep(1.6)
    r = ev(c, "(()=>{const els=[...document.querySelectorAll('*')].filter(e=>e.children.length===0&&(e.innerText||'').trim()==='工作模式设置');if(!els.length)return 'NO';els[0].click();return 'CLICKED'})()",
           'work mode')
    if isinstance(r, str) and r.startswith('NO'):
        raise SystemExit('Cannot find 工作模式设置. Clear it manually in Settings.')
    time.sleep(1.6)
    r = ev(c, "(()=>{const els=[...document.querySelectorAll('*')].filter(e=>e.children.length===0&&(e.innerText||'').trim()==='编辑');if(!els.length)return 'NO';els[els.length-1].click();return 'CLICKED'})()",
           'edit')
    if isinstance(r, str) and r.startswith('NO'):
        raise SystemExit('Cannot find 编辑. Clear it manually in Settings.')
    time.sleep(1.4)
    r = ev(c, "(()=>{const el=document.querySelector('textarea[placeholder=\"输入偏好指令\"]');if(!el)return 'NO';const s=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;s.call(el,'');el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return {len:el.value.length}})()",
           'clear')
    if not isinstance(r, dict) or r.get('len') != 0:
        raise SystemExit('Failed to clear textarea: %s' % r)
    time.sleep(0.5)
    r = ev(c, "(()=>{const b=[...document.querySelectorAll('button')].filter(e=>/保存|确定/.test((e.innerText||'').trim()));if(!b.length)return 'NO_SAVE';b[b.length-1].click();return 'SAVED'})()",
           'save')
    if r != 'SAVED':
        raise SystemExit('Save button not found. Clear it manually in Settings.')
    time.sleep(1.6)
    ev(c, "(()=>{const els=[...document.querySelectorAll('*')].filter(e=>e.children.length===0&&(e.innerText||'').trim()==='编辑');if(!els.length)return 'NO';els[els.length-1].click();return 'REOPENED'})()",
       'reopen')
    time.sleep(1.4)
    p = ev(c, "(()=>{const el=document.querySelector('textarea[placeholder=\"输入偏好指令\"]');return el?el.value.length:'NO'})()",
           'read back')
    ok = p == 0
    print('\n  preference cleared: %s (read back len=%s)' % ('PASS' if ok else 'FAIL', p))
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=9222)
    ap.add_argument('--exe')
    ap.add_argument('--no-restart', action='store_true')
    args = ap.parse_args()

    exe = find_exe(args.exe)
    if not args.no_restart and not exe:
        raise SystemExit('Cannot locate Doubao executable. Pass --exe PATH.')
    if exe:
        print('Doubao exe      :', exe)

    if not args.no_restart:
        print('Stopping current client...')
        stop_client()
        print('Starting with CDP port %d...' % args.port)
        start_client(exe, args.port)

    v = wait_cdp(args.port)
    print('CDP             :', v.get('Browser', '?'))
    t = pick_target(args.port, url_contains='doubao-chat')
    print('Target          :', (t.get('url') or '')[:80])
    c = CDP(t['webSocketDebuggerUrl'], timeout=30)
    for _ in range(30):
        try:
            if (c.evaluate("(document.body.innerText||'').length") or 0) > 300:
                break
        except Exception:
            pass
        time.sleep(1)
    ok = False
    try:
        ok = clear_pref(c)
    finally:
        c.close()

    if not args.no_restart:
        print('Restoring normal client startup...')
        stop_client()
        start_client(exe, None)
        time.sleep(3)
        print('Running processes:', len(running_pids()))

    print('\nRESULT: %s' % ('PASS - preference cleared' if ok
                            else 'FAIL - clear it manually in Settings'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
