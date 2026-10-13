# Streaming to the Mac

Current working route: H.264 at roughly 4 Mbit/s, HTTP streaming through **native IPv6 OpenSSH**, displayed by Chrome WebCodecs on localhost. No custom Chrome proxy flags are needed. Measurement processing does not wait for the Mac; each viewer has a bounded queue and slow viewers reconnect at a keyframe.

Earlier failures were separate: the camera originally used a non-data hub port; after fixing that it delivered roughly 80 FPS. Tailscale SSH transfers of JPEGs were much slower than the native SSH route in the observed session. The original JPEG preview also generated/polled at a low rate. None of that proves the USB hub currently limits detection, and no full network-capacity benchmark was performed.

## Alternative worth testing first: Tailscale Serve HTTPS

Tailscale Serve proxies a loopback service to a private HTTPS address accessible to the tailnet. This avoids the SSH stream forwarding layer and provides the secure origin WebCodecs needs. It still uses HTTP/TCP, so it does not eliminate loss-induced TCP delays or a slow underlying relayed network path. It is a comparison candidate, not a demonstrated speedup. [Official Serve documentation](https://tailscale.com/docs/features/tailscale-serve), [CLI reference](https://tailscale.com/docs/reference/tailscale-cli/serve).

Read-only inspection found `/usr/bin/tailscale` installed and **no existing Serve configuration**. Nothing was enabled or exposed. A later explicit test could run `tailscale serve --https=443 http://127.0.0.1:3090` in the foreground and open the HTTPS URL it prints. It may require tailnet HTTPS authorization and the appropriate access policy. Stop with Ctrl+C after the trial. Keep access private to the intended devices; do not use Funnel. Compare actual browser age/uncertainty and valid measurement rates under equivalent motion.

## WebRTC

WebRTC is a stronger next transport experiment when packet-loss latency matters: it supports real-time media transport and congestion handling instead of a long HTTP byte stream. It requires signaling, ICE connectivity, secure media, codec negotiation and receiver feedback; merely replacing an HTTP URL cannot provide it. [GStreamer webrtcbin documentation](https://gstreamer.freedesktop.org/documentation/webrtc/), [WebRTC protocols](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API/Protocols).

The Jetson has `webrtcbin`, but `gst-inspect-1.0 nicesrc` fails: the installed runtime is missing the required ICE source element for that route. No packages, firewall rules, certificates or network settings were changed. A tested WebRTC implementation is a follow-up, not included in this version. It could reuse the software H.264 encoder, but the Jetson Orin Nano does not have a hardware NVENC encoder; changing transport does not remove encoding cost. [NVIDIA software encoding guidance](https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/SD/Multimedia/SoftwareEncodeInOrinNano.html).

## Direct LAN connection

A shared wired network is another possible comparison if available. The previously observed Mac and Jetson IPv4 addresses were on separate isolated networks despite looking identical, so direct IPv4 connectivity was not established. Do not expose this unauthenticated calibration dashboard on all interfaces or the public IPv6 address. A private network route plus authenticated TLS/reverse proxy needs deliberate setup; localhost/native SSH remains the verified fallback.

For reliable 80 FPS measurements, prioritize detection cost and lighting first. Network improvements affect the view and dashboard age; they do not recover frames rejected by the detector. `--video-fps 60` can reduce software encoder competition while leaving 80 FPS measurement capture intact.
