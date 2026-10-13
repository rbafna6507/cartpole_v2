# Arduino dependency snapshot

`FastAccelStepper-1.2.8.zip` is the local library snapshot previously used by
the standalone cart sine sketch. Upstream: https://github.com/gin66/FastAccelStepper

- Version: **1.2.8**
- SHA-256: `4d9f8f17a88fb793a11c0793be8fd143ea7d1311b1ab6a0024176f12930557e8`
- License files in the archive: FastAccelStepper-1.2.8/LICENSE

Install the ZIP through Arduino IDE's **Sketch → Include Library → Add .ZIP Library**.
`scripts/build_cart_sketches.sh` extracts it to a temporary directory for CLI
builds; no global library installation or network download is needed.
The ESP32 Arduino core and Arduino CLI must already be installed. The verified
core version is **esp32:esp32 3.3.2**.

The library source used by other firmware in the old workspace remains there.
Build products and extracted dependencies are kept outside this repository.
