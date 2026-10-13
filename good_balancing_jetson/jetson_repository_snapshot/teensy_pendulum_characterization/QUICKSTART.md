# What to do first

1. Upload `teensy_pendulum_characterization.ino` as Teensy 4.1 / USB Serial. Keep your current wiring: AS5600 on **Wire1 SDA17/SCL16**, cart STEP2/DIR3, shared ENABLE8.
2. Secure vertical axes/rail, because ENABLE8 is shared by all drivers. For passive tests fix the cart; for cart-motion tests remove that clamp.
3. In this directory:

```bash
python3 -m pip install -r requirements.txt
python3 lab.py ports
python3 lab.py measurements
python3 lab.py --port PORT noise --seconds 10
python3 lab.py --port PORT static
python3 lab.py --port PORT swing --angle 20 --fit
python3 lab.py --port PORT swing --angle -20 --fit
```

Replace PORT with the actual port. Repeat each ±20° release three times. Position and hold before pressing Enter, then wait for “Release now.” Add ±45° and ±75° recordings next. Use a protractor for static checks; the requested angle is physical angle from hanging down.

4. First powered test (the program guides manual endpoint marking and centering):

```bash
python3 lab.py --port PORT drive --distance 5 --speed 10 --accel 100 --jerk 1000 --single
```

Verify direction and actual travel with a ruler. If correct, run:

```bash
python3 lab.py --port PORT drive --distance 20 --speed 30 --accel 300 --jerk 3000 --repeats 2
python3 lab.py --port PORT timing --count 200
python3 lab.py summary runs
```

5. ZIP and send the entire `runs` directory. Include mass/COM measurements and whether the arm/weights changed from the earlier recordings. The source now describes a 125 mm arm and two 5.85 g weights; confirm current dimensions.

All drives require a fresh manual centre reference. These tests log emitted pulses, not independent cart position. No limit switches, Ethernet control, camera pipeline, swing-up or RL policy are active in this characterization build. See README for stopping behavior, constraints and output definitions.
