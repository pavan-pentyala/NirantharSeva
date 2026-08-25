# Recording script — the real-phone airplane-mode clip

`docs/IMPLEMENTATION_PLAN.md` §8.5's Review-III fallback: *"Airplane-mode
demo on a real phone via add-to-home-screen. Record it now while it is
fresh."* This is the one P9.3 deliverable this session genuinely cannot
complete — it needs your own physical phone. What this session *can* do,
and did, is verify the technical setup below actually works, so recording
it is a recording, not a debugging session.

## The one thing this script gets right that a casual attempt won't

**Don't point your phone's browser at your laptop's LAN IP on port
5173.** Two separate reasons, both real:

1. **Port 5173 is the Vite *dev* server, not the built app.** This
   project's own history already found that `vite-plugin-pwa`'s
   `injectManifest` mode only produces a real, installable
   service-worker precache in a **production build** — the dev server's
   precache is empty (`docs/OBSERVATIONS.md` observation 33,
   `PROGRESS.md`'s own P4.3 exit-criteria note). Use the **built preview
   server, port 4173**, confirmed this session to serve a real 7-entry,
   341 KiB precache with a working manifest and both icon sizes.
2. **A bare LAN IP over plain HTTP is not a "secure context."** Chrome
   (and most mobile browsers) refuse to register a service worker, and
   often refuse a clean "Add to Home Screen" prompt, over `http://` to
   anything other than `localhost`/`127.0.0.1`. A phone visiting
   `http://192.168.x.x:4173` directly will likely see a broken or
   missing install prompt — not because the app is wrong, but because
   the browser doesn't trust the connection.

The fix professional Android testing uses is **USB debugging + `adb
reverse`**, which makes the phone's own browser treat the tunnel as
`localhost` — a real secure context, no external service, no certificate.

## Setup (verified this session, up to the point a real device is needed)

```bash
docker compose exec client npm run build
docker compose exec -d client npm run preview
```
Confirmed working this session: `http://localhost:4173/` → 200,
`http://localhost:4173/manifest.webmanifest` → valid (name, `display:
standalone`, `start_url: /login`, both icon sizes), `icon-192.png` /
`icon-512.png` / `sw.js` all → 200. This is the real thing to point a
phone at.

### If your phone is Android (recommended path — fully local, no tunnel)

1. On the phone: Settings → About phone → tap "Build number" 7 times to
   enable Developer Options, then Settings → Developer Options → enable
   USB debugging.
2. Install [Android platform-tools](https://developer.android.com/tools/releases/platform-tools)
   on this machine if `adb` isn't already available (`adb --version`).
3. Connect the phone by USB. Accept the "Allow USB debugging?" prompt on
   the phone. Confirm: `adb devices` should list it as `device`, not
   `unauthorized`.
4. `adb reverse tcp:4173 tcp:4173`
5. On the phone's Chrome: navigate to `http://localhost:4173/login` —
   this now reaches your laptop's `:4173` through the USB tunnel, and
   Chrome treats it as `localhost`, a secure context.

### If your phone is iPhone (fallback — needs a temporary HTTPS tunnel)

iOS Safari has no USB port-forwarding equivalent to `adb reverse`.
Use a temporary tunnel for the recording only, e.g.:
```bash
npx localtunnel --port 4173
# or: ngrok http 4173
```
Either gives a real `https://` URL that both satisfies the secure-context
requirement and works from any network — but it's an external service for
the duration of the recording, not a fully local setup. Tear it down
(Ctrl+C) as soon as you're done; don't leave a tunnel to your dev machine
open.

## Shot list

Single continuous take is fine here — this clip is about proving the
mechanism is real, not about pacing.

| # | Shot | What to show |
|---|---|---|
| 1 | Open the app | Chrome (or Safari) → the URL from setup above → login screen. Log in as `asha_a` / `dev`. |
| 2 | Add to Home Screen | Browser menu → "Add to Home Screen" / the install prompt if Chrome offers one automatically. Show the icon landing on the home screen. |
| 3 | Open from home screen | Tap the new icon — it should open standalone (no browser chrome), confirming `display: standalone` took effect. |
| 4 | Airplane mode | Turn it on, on camera. |
| 5 | Create a referral | `/referrals/new`, fill it in, save. Show the "saved on your phone / no signal" confirmation — the same offline-first path as the DevTools version, now proven on real hardware with the network interface physically cut, not simulated. |
| 6 | Restore signal | Airplane mode off. |
| 7 | Show it synced | Reopen the referral or the list — the "waiting to send" indicator should be gone. If you have a second device or window on `supervisor1`'s dashboard, showing the referral arrive there is the strongest possible close. |

## What this session could and couldn't verify

**Could:** the built app's real precache, manifest, and icons all serve
correctly from `:4173` (curl-verified above) — the server-side half of
this is genuinely proven, not assumed. **Could not:** the phone-side half
— `adb reverse`, the actual "Add to Home Screen" prompt, airplane mode,
and the real sync-on-reconnect — none of that can run inside this
session. It's described here from established, standard practice, not
independently executed. Note anything that needed a different step than
this document describes when you actually record it.
