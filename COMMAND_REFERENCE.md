# Command-line argument reference

Generated from actual `--help` output on October 23, 2026. Start with [COMMAND_CHEATSHEET.md](COMMAND_CHEATSHEET.md) for workflows and defaults. Help commands were run without serial connections, training, or service changes. These are CLI options; interactive console commands are listed in the cheat sheet.

## cartpole / cartpole-console

```text
usage: operator.py [-h] [--dry-run] [--rt-priority RT_PRIORITY]
                   [--no-affinity] [--no-camera]
                   [--camera-service CAMERA_SERVICE]
                   [--camera-cpus CAMERA_CPUS] [--control-cpus CONTROL_CPUS]

One-command operator launcher; help and dry-run never access the rig.

options:
  -h, --help
  --dry-run             Print the launch plan; no serial, sudo or affinity
                        changes.
  --rt-priority RT_PRIORITY
                        Child SCHED_RR priority 0..99; 0 explicitly disables
                        realtime (default 10).
  --no-affinity         Explicitly disable CPU partitioning.
  --no-camera           Partition control CPUs without changing camera
                        affinity.
  --camera-service CAMERA_SERVICE
  --camera-cpus CAMERA_CPUS
  --control-cpus CONTROL_CPUS

Console options (launcher defaults: port from CARTPOLE_PORT or installed Teensy, rate 250, keep board parameters):
usage: operator.py [-h] --port PORT [--rate {0,100,250,500,1000}]
                   [--log-dir LOG_DIR]
                   [--vision-telemetry-port VISION_TELEMETRY_PORT]
                   [--no-vision-telemetry] [--hanging-model HANGING_MODEL]
                   [--calibration-identity CALIBRATION_IDENTITY]
                   [--ideal-half-turn]
                   [--command {auto,bal,manual,velocity,stop,center,home,rehome,upright,hanging,status,info,clear,params,get,set,save,load,policy-zero,policy-run,python-auto,python-bal}]
                   [--actor ACTOR] [--development-only] [--duration DURATION]
                   [--switches {on,off}] [--center-confirmed] [--param PARAM]
                   [--value VALUE] [--profile PROFILE]
                   [--startup-profile STARTUP_PROFILE | --keep-board-params]
                   [--velocity VELOCITY] [--ttl-ms TTL_MS]
                   [--source {magnetic-step}]

Operator console for board reference modes and explicit external policies.

options:
  -h, --help            show this help message and exit
  --port PORT
  --rate {0,100,250,500,1000}
  --log-dir LOG_DIR
  --vision-telemetry-port VISION_TELEMETRY_PORT
                        read-only loopback encoder mirror port (default 3096;
                        0 disables)
  --no-vision-telemetry
                        disable loopback encoder mirror
  --hanging-model HANGING_MODEL
                        approved hanging calibration model JSON
  --calibration-identity CALIBRATION_IDENTITY
                        separate current installation identity JSON
  --ideal-half-turn     explicitly assume hanging is exactly opposite upright
  --command {auto,bal,manual,velocity,stop,center,home,rehome,upright,hanging,status,info,clear,params,get,set,save,load,policy-zero,policy-run,python-auto,python-bal}
  --actor ACTOR         validated numeric actor JSON for --command policy-run
  --development-only    acknowledge unqualified learned policy execution
  --duration DURATION   motion duration (default 10s; learned policy 5s), HOME
                        timeout (75s), or REHOME timeout (15.25s)
  --switches {on,off}   explicit stopped physical switch profile selection
  --center-confirmed    operator asserts cart is physically centered now
  --param PARAM         parameter name for get or set
  --value VALUE         parameter value for set
  --profile PROFILE     profile path for save or load
  --startup-profile STARTUP_PROFILE
                        apply this profile instead of the preserved tuned
                        default
  --keep-board-params   keep live board parameters; disable automatic startup
                        profile
  --velocity VELOCITY
  --ttl-ms TTL_MS
  --source {magnetic-step}
                        explicit source/frame selection for external Python
                        policies
```

## cartpole-view-policy

```text
usage: policy_viewer.py [-h] [--controller {learned,reference}]
                        [--actor ACTOR] [--experiment EXPERIMENT]
                        [--start {hanging,upright}] [--seed SEED]
                        [--seconds SECONDS] [--duration DURATION] [--headless]

Local native viewer for numeric actors and the saved reference controller.
Learned mode uses the actual 100 Hz RigCartpoleEnv and numeric SDK actor.
Reference mode uses the same fitted plant with the 1 kHz ReferencePolicy,
saved gains and ideal sensors; its output is already governed, so no second
governor is applied. Imports create no window and no hardware connection. GUI
state is display-only.

options:
  -h, --help            show this help message and exit
  --controller {learned,reference}
  --actor ACTOR
  --experiment EXPERIMENT
                        Exact training experiment JSON or protocol containing
                        experiment.
  --start {hanging,upright}
  --seed SEED
  --seconds SECONDS     Simulation horizon, .01..60 (default 25).
  --duration DURATION   Close window after this many wall-clock seconds.
  --headless            Run same episode without opening a window.
```

## cartpole-v2-view

```text
usage: viewer.py [-h] [--start {auto,upright}] [--seed SEED]
                 [--duration DURATION]

Interactive SDK reference controller in MuJoCo.

options:
  -h, --help            show this help message and exit
  --start {auto,upright}
  --seed SEED
  --duration DURATION   close after this many wall seconds
```

## cartpole-v2

```text
usage: cli.py [-h] {import-console,import-vision,inspect,replay,simulate} ...

Cartpole SDK: local recordings, policy replay and optional MuJoCo simulation.

positional arguments:
  {import-console,import-vision,inspect,replay,simulate}
    import-console      Import baseline console CSV into one recording per
                        board-clock segment.
    import-vision       Import vision3 states JSONL from one calibration
                        epoch.
    inspect             Validate a recording and summarize sources and
                        quality.
    replay              Run the illustrative angular-damping policy offline.
    simulate            Run a local closed-loop MuJoCo experiment (requires
                        sim extra).

options:
  -h, --help            show this help message and exit
```

## cartpole-v2 import-console

```text
usage: cli.py import-console [-h] --session-id SESSION_ID --frame-id FRAME_ID
                             input output

Import baseline console CSV into one recording per board-clock segment.

positional arguments:
  input
  output                New directory for console segments; new file for
                        vision.

options:
  -h, --help            show this help message and exit
  --session-id SESSION_ID
                        Unique identity for this recording/run.
  --frame-id FRAME_ID   Explicit calibration/coordinate-frame identity.
```

## cartpole-v2 import-vision

```text
usage: cli.py import-vision [-h] --session-id SESSION_ID --frame-id FRAME_ID
                            input output

Import vision3 states JSONL from one calibration epoch.

positional arguments:
  input
  output                New directory for console segments; new file for
                        vision.

options:
  -h, --help            show this help message and exit
  --session-id SESSION_ID
                        Unique identity for this recording/run.
  --frame-id FRAME_ID   Explicit calibration/coordinate-frame identity.
```

## cartpole-v2 inspect

```text
usage: cli.py inspect [-h] recording

positional arguments:
  recording

options:
  -h, --help  show this help message and exit
```

## cartpole-v2 replay

```text
usage: cli.py replay [-h]
                     [--source {fused,magnetic,magnetic_filtered,simulation,step,vision}]
                     [--joint JOINT] --frame-id FRAME_ID [--gain GAIN]
                     recording output

positional arguments:
  recording
  output                New trace file; existing files are never overwritten.

options:
  -h, --help            show this help message and exit
  --source {fused,magnetic,magnetic_filtered,simulation,step,vision}
  --joint JOINT
  --frame-id FRAME_ID
  --gain GAIN           Illustrative offline damping gain.
```

## cartpole-v2 simulate

```text
usage: cli.py simulate [-h] [--steps STEPS] [--seed SEED]
                       [--controller {reference,zero}]
                       [--start {auto,upright}] [--state X V THETA OMEGA]
                       [--model-config MODEL_CONFIG]
                       [--sensor-config SENSOR_CONFIG]
                       output

positional arguments:
  output                New output directory, never overwritten.

options:
  -h, --help            show this help message and exit
  --steps STEPS         Maximum control intervals (default: 10,000).
  --seed SEED
  --controller {reference,zero}
  --start {auto,upright}
  --state X V THETA OMEGA
                        Initial SI state; default hanging, or theta=.04 for
                        upright start.
  --model-config MODEL_CONFIG
                        JSON object overriding provisional SimulationConfig
                        fields.
  --sensor-config SENSOR_CONFIG
                        JSON object overriding SensorConfig fields.
```

## cartpole-id

```text
usage: cli.py [-h]
              {inspect,collect-passive,collect-pulse,recover-passive,review-recording,review-releases,review-fit,annotations-template,fit-passive,fit-driven,assumptions-template,export-model,gym-smoke}
              ...

Operator procedures for immutable collection, fitting and scoped simulation.

positional arguments:
  {inspect,collect-passive,collect-pulse,recover-passive,review-recording,review-releases,review-fit,annotations-template,fit-passive,fit-driven,assumptions-template,export-model,gym-smoke}
    inspect             Read saved reference, home, health and live parameters
                        in a stopped session.
    collect-passive     Record operator-released oscillations with the motor
                        disabled; physically restrain the cart.
    collect-pulse       Execute one allowlisted cart pulse then12s feedback
                        hold; requires --execute.
    recover-passive     Explicitly review a passive KeyboardInterrupt and
                        preserve a separate recovery decision; never rewrite
                        raw evidence.
    review-recording    Check completed raw data and plot observations without
                        fitting or selecting intervals.
    review-releases     Compare raw camera/encoder relative hanging and
                        qualify explicitly annotated release poses; no
                        fitting.
    review-fit          Plot frozen passive-fit predictions on the exact
                        validation data; never refit or change acceptance.
    annotations-template
                        Create an explicit manual free-release annotation
                        template; never select fit windows automatically.
    fit-passive         Fit training-only passive dynamics and score
                        independently annotated validation releases.
    fit-driven          Run the existing strict driven pendulum fitter using
                        raw theta and MCU acceleration.
    assumptions-template
                        Create an editable complete provisional simulation
                        configuration at100Hz; values remain assumptions.
    export-model        Export an accepted scoped fit with explicit
                        assumptions; unsupported dynamics fail closed.
    gym-smoke           Load an exported model and run a bounded headless
                        zero-action check; no hardware/RL claim.

options:
  -h, --help            show this help message and exit

Help and offline commands never open serial. See docs/system-identification-
workflow.md for purpose, annotations and model limits.
```

## cartpole-id inspect

```text
usage: cli.py inspect [-h] --port PORT --output OUTPUT
                      [--expected-reference EXPECTED_REFERENCE]
                      [--expected-home EXPECTED_HOME]

Read saved reference, home, health and live parameters in a stopped session.

options:
  -h, --help            show this help message and exit
  --port PORT           Explicit serial device; no discovery, home, clear or
                        calibration.
  --output OUTPUT       New immutable run directory, including failure
                        evidence.
  --expected-reference EXPECTED_REFERENCE
                        Optional exact saved upright raw encoder reference.
  --expected-home EXPECTED_HOME
                        Optional exact current home epoch.
```

## cartpole-id collect-passive

```text
usage: cli.py collect-passive [-h] --port PORT --output OUTPUT
                              [--expected-reference EXPECTED_REFERENCE]
                              [--expected-home EXPECTED_HOME]
                              [--dataset-role {training,validation,development}]
                              [--run-label RUN_LABEL]
                              [--camera-url CAMERA_URL | --no-camera]
                              [--seconds SECONDS]
                              [--release-angles-deg RELEASE_ANGLES_DEG [RELEASE_ANGLES_DEG ...]]
                              [--release-directions {left,right} [{left,right} ...]]
                              [--repetitions REPETITIONS]
                              [--cart-restraint CART_RESTRAINT]

Record operator-released oscillations with the motor disabled; physically
restrain the cart.

options:
  -h, --help            show this help message and exit
  --port PORT           Explicit serial device; no discovery, home, clear or
                        calibration.
  --output OUTPUT       New immutable run directory, including failure
                        evidence.
  --expected-reference EXPECTED_REFERENCE
                        Optional exact saved upright raw encoder reference.
  --expected-home EXPECTED_HOME
                        Optional exact current home epoch.
  --dataset-role {training,validation,development}
  --run-label RUN_LABEL
                        Descriptive immutable recording label.
  --camera-url CAMERA_URL
                        Raw sensing-stream URL; must become ready before
                        serial collection.
  --no-camera           Pulse only: explicitly record missing independent
                        camera evidence; passive collection requires camera.
  --seconds SECONDS     Maximum recording duration, 1..180s; type done then
                        Enter to finish early after recording begins.
  --release-angles-deg RELEASE_ANGLES_DEG [RELEASE_ANGLES_DEG ...]
                        Requested degrees away from hanging; labels are not
                        measured angles.
  --release-directions {left,right} [{left,right} ...]
                        Directions in camera view.
  --repetitions REPETITIONS
  --cart-restraint CART_RESTRAINT
                        How you will keep the cart fixed; required with
                        requested angles.
```

## cartpole-id collect-pulse

```text
usage: cli.py collect-pulse [-h] --port PORT --output OUTPUT
                            [--expected-reference EXPECTED_REFERENCE]
                            [--expected-home EXPECTED_HOME]
                            [--dataset-role {training,validation,development}]
                            [--run-label RUN_LABEL]
                            [--camera-url CAMERA_URL | --no-camera]
                            [--pulse-seconds {0.45,0.65,0.8,1.0}]
                            [--hold-seconds HOLD_SECONDS] [--execute]
                            --amplitude-mm {-30,-20,-10,-5,5,10,20,30}

Execute one allowlisted cart pulse then12s feedback hold; requires --execute.

options:
  -h, --help            show this help message and exit
  --port PORT           Explicit serial device; no discovery, home, clear or
                        calibration.
  --output OUTPUT       New immutable run directory, including failure
                        evidence.
  --expected-reference EXPECTED_REFERENCE
                        Optional exact saved upright raw encoder reference.
  --expected-home EXPECTED_HOME
                        Optional exact current home epoch.
  --dataset-role {training,validation,development}
  --run-label RUN_LABEL
                        Descriptive immutable recording label.
  --camera-url CAMERA_URL
                        Raw sensing-stream URL; must become ready before
                        serial collection.
  --no-camera           Pulse only: explicitly record missing independent
                        camera evidence; passive collection requires camera.
  --pulse-seconds {0.45,0.65,0.8,1.0}
                        Pulse duration; unsafe amplitude/duration pairs fail
                        before serial. Default0.65s.
  --hold-seconds HOLD_SECONDS
                        Explicit3..12s active cart feedback hold,
                        default12s;20ms leases are unchanged.
  --execute             Authorize this invocation to issue ARM and
                        acceleration requests.
  --amplitude-mm {-30,-20,-10,-5,5,10,20,30}
                        Signed pulse amplitude; begin with5mm and inspect
                        before escalating.
```

## cartpole-id recover-passive

```text
usage: cli.py recover-passive [-h] --input INPUT --reason REASON

options:
  -h, --help       show this help message and exit
  --input INPUT    Local Rig JSONL or JSONL.gz with its original sibling
                   reports and camera evidence.
  --reason REASON  Why the operator interrupted this passive recording;
                   required for the recovery audit.
```

## cartpole-id review-recording

```text
usage: cli.py review-recording [-h] --input INPUT --output OUTPUT

options:
  -h, --help       show this help message and exit
  --input INPUT
  --output OUTPUT
```

## cartpole-id review-releases

```text
usage: cli.py review-releases [-h] --input INPUT --annotations ANNOTATIONS
                              --output OUTPUT

options:
  -h, --help            show this help message and exit
  --input INPUT
  --annotations ANNOTATIONS
  --output OUTPUT
```

## cartpole-id review-fit

```text
usage: cli.py review-fit [-h] --fit FIT --validation VALIDATION
                         --validation-annotations VALIDATION_ANNOTATIONS
                         --output OUTPUT

options:
  -h, --help            show this help message and exit
  --fit FIT
  --validation VALIDATION
  --validation-annotations VALIDATION_ANNOTATIONS
  --output OUTPUT
```

## cartpole-id annotations-template

```text
usage: cli.py annotations-template [-h] --input INPUT --output OUTPUT

options:
  -h, --help       show this help message and exit
  --input INPUT    Rig JSONL, JSONL.gz, or archive.tar.gz::exact/member.jsonl
  --output OUTPUT
```

## cartpole-id fit-passive

```text
usage: cli.py fit-passive [-h] --training TRAINING --training-annotations
                          TRAINING_ANNOTATIONS --validation VALIDATION
                          --validation-annotations VALIDATION_ANNOTATIONS
                          [--model {viscous,viscous_coulomb}] --output OUTPUT

options:
  -h, --help            show this help message and exit
  --training TRAINING
  --training-annotations TRAINING_ANNOTATIONS
  --validation VALIDATION
  --validation-annotations VALIDATION_ANNOTATIONS
  --model {viscous,viscous_coulomb}
                        Declare before examining validation; never select the
                        winner from validation.
  --output OUTPUT
```

## cartpole-id fit-driven

```text
usage: cli.py fit-driven [-h] --training TRAINING --validation VALIDATION
                         --output OUTPUT

options:
  -h, --help            show this help message and exit
  --training TRAINING
  --validation VALIDATION
  --output OUTPUT
```

## cartpole-id assumptions-template

```text
usage: cli.py assumptions-template [-h] --output OUTPUT

options:
  -h, --help       show this help message and exit
  --output OUTPUT
```

## cartpole-id export-model

```text
usage: cli.py export-model [-h] --report REPORT --scope {passive-down,driven}
                           --assumptions ASSUMPTIONS --output OUTPUT

options:
  -h, --help            show this help message and exit
  --report REPORT
  --scope {passive-down,driven}
  --assumptions ASSUMPTIONS
  --output OUTPUT
```

## cartpole-id gym-smoke

```text
usage: cli.py gym-smoke [-h] --model MODEL [--steps STEPS] --output OUTPUT

options:
  -h, --help       show this help message and exit
  --model MODEL
  --steps STEPS
  --output OUTPUT
```

## cartpole-vision

```text
usage: live.py [-h] [--camera CAMERA] [--width WIDTH] [--height HEIGHT]
               [--fps FPS] [--rotate {0,90,180,270}] [--view-bind VIEW_BIND]
               [--view-port VIEW_PORT] [--view-tcp-mss VIEW_TCP_MSS]
               [--port PORT] [--preview-fps PREVIEW_FPS]
               [--detector-width DETECTOR_WIDTH]
               [--opencv-threads OPENCV_THREADS] [--video-fps VIDEO_FPS]
               [--no-video] [--video-bitrate VIDEO_BITRATE]
               [--gst-python GST_PYTHON] [--calibration-file CALIBRATION_FILE]
               [--encoder-port ENCODER_PORT] [--encoder-sign {-1,1}]
               [--vision-delay-ms VISION_DELAY_MS]
               [--camera-timeout CAMERA_TIMEOUT]
               [--keep-sessions KEEP_SESSIONS] [--log-file LOG_FILE]
               [--sdk-port SDK_PORT] [--out OUT] [--record]
               [--duration DURATION] [--exposure-raw EXPOSURE_RAW]
               [--auto-exposure-raw AUTO_EXPOSURE_RAW] [--gain-raw GAIN_RAW]

Run the observe-only cartpole vision dashboard.

options:
  -h, --help            show this help message and exit
  --camera CAMERA
  --width WIDTH
  --height HEIGHT
  --fps FPS
  --rotate {0,90,180,270}
  --view-bind VIEW_BIND
                        Optional exact tailnet IPv4 for remote viewing;
                        calibration stays on loopback
  --view-port VIEW_PORT
  --view-tcp-mss VIEW_TCP_MSS
                        Optional private listener TCP MSS, 536..1220 bytes;
                        use only after network measurement
  --port PORT
  --preview-fps PREVIEW_FPS
  --detector-width DETECTOR_WIDTH
                        Detection image width; endpoints remain in camera
                        coordinates
  --opencv-threads OPENCV_THREADS
  --video-fps VIDEO_FPS
                        H.264 frame-rate cap; defaults to capture FPS
  --no-video            Disable H.264 to measure tracking without video
                        encoding load
  --video-bitrate VIDEO_BITRATE
                        H.264 target bitrate, kbit/s
  --gst-python GST_PYTHON
                        Python with the installed GStreamer GI runtime
  --calibration-file CALIBRATION_FILE
                        Restore saved vision reference for identical camera
                        geometry; update it on calibration changes
  --encoder-port ENCODER_PORT
                        Loopback UDP feed from console; 0 disables
  --encoder-sign {-1,1}
                        Encoder direction relative to image-right
  --vision-delay-ms VISION_DELAY_MS
                        Measured camera delay to subtract from host-read
                        timestamp
  --camera-timeout CAMERA_TIMEOUT
                        Exit on stalled camera so a supervisor can restart
  --keep-sessions KEEP_SESSIONS
                        Bounded telemetry sessions retained; recorded sessions
                        are never pruned
  --log-file LOG_FILE   Optional rotating runtime diagnostics, 8 MiB maximum
  --sdk-port SDK_PORT   Loopback SDK shadow telemetry; 0 disables
  --out OUT
  --record
  --duration DURATION   Stop automatically after this many seconds
  --exposure-raw EXPOSURE_RAW
                        Backend-specific exposure value; acceptance/readback
                        logged
  --auto-exposure-raw AUTO_EXPOSURE_RAW
                        Backend-specific auto-exposure mode
  --gain-raw GAIN_RAW   Backend-specific gain value
```

## cartpole-portal

```text

```

## cartpole-worker

```text

```

## scripts/cartpole-release

```text
usage: release.py [-h] {build,install,activate} ...

Build and install trusted operator releases, without serial or service access.
This is deployment tooling for the repository owner's source, not a sandbox
for public submissions. Only install bundles produced from source you trust.

positional arguments:
  {build,install,activate}
    build               Package committed source and required model/protocol
                        inputs.
    install             Install a trusted bundle into a new release directory;
                        offline checks only.
    activate            Select an already verified release; does not start a
                        console.

options:
  -h, --help            show this help message and exit
```

## scripts/cartpole-release build

```text
usage: release.py build [-h] [--repo REPO] --name NAME --output OUTPUT

options:
  -h, --help       show this help message and exit
  --repo REPO
  --name NAME
  --output OUTPUT
```

## scripts/cartpole-release install

```text
usage: release.py install [-h] --archive ARCHIVE [--root ROOT] [--uv UV]
                          [--python PYTHON] [--no-activate]
                          [--bin-dir BIN_DIR]

options:
  -h, --help         show this help message and exit
  --archive ARCHIVE
  --root ROOT
  --uv UV
  --python PYTHON
  --no-activate
  --bin-dir BIN_DIR  Also install stable cartpole/cartpole-console PATH
                     wrappers here.
```

## scripts/cartpole-release activate

```text
usage: release.py activate [-h] [--root ROOT] --name NAME

options:
  -h, --help   show this help message and exit
  --root ROOT
  --name NAME
```

## combined training/evaluation

```text
usage: run.py [-h] {train,evaluate} ...

Evidence-only filtered BAL actor transfer into existing combined PPO
components.

positional arguments:
  {train,evaluate}

options:
  -h, --help        show this help message and exit
```

## combined training/evaluation train

```text
usage: run.py train [-h] [--protocol PROTOCOL] --output OUTPUT --arm
                    {ppo,retained} --seed SEED [--budget {pilot,long}]
                    [--smoke]

options:
  -h, --help            show this help message and exit
  --protocol PROTOCOL
  --output OUTPUT
  --arm {ppo,retained}
  --seed SEED
  --budget {pilot,long}
  --smoke
```

## combined training/evaluation evaluate

```text
usage: run.py evaluate [-h] [--protocol PROTOCOL] --run RUN --step STEP
                       --output OUTPUT [--confirmation] [--stress] [--numeric]

options:
  -h, --help           show this help message and exit
  --protocol PROTOCOL
  --run RUN
  --step STEP
  --output OUTPUT
  --confirmation
  --stress
  --numeric
```

## scripts/balance-error-learning

```text
usage: error_training.py [-h] {train,evaluate} ...

Offline balance learning with explicit actor-input angle errors. This
perturbation is not a calibrated encoder law. Physics, telemetry, truth
reward, validity, ages and angular rate retain their existing definitions. No
hardware API, SDK actor export, or acceptance transition is provided.

positional arguments:
  {train,evaluate}
    train           New teacher-initialized offline trial; no actor export.
    evaluate        Fixed angle-error matrix on new independent pose seeds.

options:
  -h, --help        show this help message and exit
```

## scripts/balance-error-learning train

```text
usage: error_training.py train [-h] --profile PROFILE --output OUTPUT --seed
                               SEED --bias-degrees BIAS_DEGREES
                               [--observer-bw {6,8,10}] [--steps STEPS]
                               [--every EVERY]
                               [--imitation-updates IMITATION_UPDATES]
                               [--seconds SECONDS]
                               [--evaluation-seconds EVALUATION_SECONDS]
                               [--training-seeds TRAINING_SEEDS [TRAINING_SEEDS ...]]
                               [--evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]]
                               [--learning-rate LEARNING_RATE]
                               [--policy-std POLICY_STD]

options:
  -h, --help            show this help message and exit
  --profile PROFILE
  --output OUTPUT
  --seed SEED
  --bias-degrees BIAS_DEGREES
  --observer-bw {6,8,10}
  --steps STEPS
  --every EVERY
  --imitation-updates IMITATION_UPDATES
  --seconds SECONDS
  --evaluation-seconds EVALUATION_SECONDS
  --training-seeds TRAINING_SEEDS [TRAINING_SEEDS ...]
  --evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]
  --learning-rate LEARNING_RATE
  --policy-std POLICY_STD
```

## scripts/balance-error-learning evaluate

```text
usage: error_training.py evaluate [-h] --output OUTPUT --seeds SEEDS
                                  [SEEDS ...] [--seconds SECONDS]
                                  [--checkpoint CHECKPOINT]
                                  run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --output OUTPUT
  --seeds SEEDS [SEEDS ...]
  --seconds SECONDS
  --checkpoint CHECKPOINT
```

## scripts/balance-learning

```text
usage: balance_learning.py [-h] {train,evaluate} ...

Matched local balance learning and longer evaluation. Never connects to
hardware.

positional arguments:
  {train,evaluate}

options:
  -h, --help        show this help message and exit
```

## scripts/balance-learning train

```text
usage: balance_learning.py train [-h] --profile PROFILE --output OUTPUT
                                 --initialization {scratch,teacher}
                                 [--gains GAINS] --seed SEED
                                 [--constraint {none,equilibrium}]
                                 [--steps STEPS] [--every EVERY]
                                 [--seconds SECONDS]
                                 [--evaluation-seconds EVALUATION_SECONDS]
                                 [--evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]]
                                 [--learning-rate LEARNING_RATE]
                                 [--policy-std POLICY_STD]
                                 [--imitation-updates IMITATION_UPDATES]

options:
  -h, --help            show this help message and exit
  --profile PROFILE
  --output OUTPUT
  --initialization {scratch,teacher}
  --gains GAINS
  --seed SEED
  --constraint {none,equilibrium}
  --steps STEPS
  --every EVERY
  --seconds SECONDS
  --evaluation-seconds EVALUATION_SECONDS
  --evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]
  --learning-rate LEARNING_RATE
  --policy-std POLICY_STD
  --imitation-updates IMITATION_UPDATES
```

## scripts/balance-learning evaluate

```text
usage: balance_learning.py evaluate [-h] --output OUTPUT --seeds SEEDS
                                    [SEEDS ...] [--seconds SECONDS]
                                    [--checkpoint CHECKPOINT]
                                    [--starts {upright,hanging} [{upright,hanging} ...]]
                                    run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --output OUTPUT
  --seeds SEEDS [SEEDS ...]
  --seconds SECONDS
  --checkpoint CHECKPOINT
  --starts {upright,hanging} [{upright,hanging} ...]
```

## scripts/colab-training

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training start

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training status

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training download

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training watch

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training stop

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training start start

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training start status

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training start download

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training start watch

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training start stop

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training status start

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training status status

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training status download

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training status watch

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training status stop

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training download start

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training download status

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training download download

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training download watch

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training download stop

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training watch start

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training watch status

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training watch download

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training watch watch

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training watch stop

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training stop start

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training stop status

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training stop download

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training stop watch

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/colab-training stop stop

```text
usage: colab_training.py [-h] --session SESSION [--colab COLAB]
                         [--output OUTPUT] [--state-file STATE_FILE]
                         [--poll-seconds POLL_SECONDS]
                         [--max-seconds MAX_SECONDS]
                         {start,status,download,watch,stop} bundle

Operate an explicit Colab CLI session. start allocates a real CPU VM and
launches training.

positional arguments:
  {start,status,download,watch,stop}
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION     Unique named Colab session for this experiment.
  --colab COLAB
  --output OUTPUT       New local results ZIP; required for download.
  --state-file STATE_FILE
                        Pinned CLI session registry; existing names cannot be
                        reallocated.
  --poll-seconds POLL_SECONDS
  --max-seconds MAX_SECONDS
```

## scripts/prepare-colab-training

```text
usage: prepare_colab_training.py [-h] --profile PROFILE --output OUTPUT
                                 [--steps STEPS] [--seed SEED]
                                 [--seconds SECONDS]
                                 [--checkpoint-every CHECKPOINT_EVERY]
                                 [--evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]]

Validate and package a selected training profile; never connects to Colab or
the rig.

options:
  -h, --help            show this help message and exit
  --profile PROFILE
  --output OUTPUT
  --steps STEPS
  --seed SEED
  --seconds SECONDS
  --checkpoint-every CHECKPOINT_EVERY
  --evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]
```

## scripts/prepare-rig-training

```text
usage: prepare_rig_training.py [-h] [--repo REPO] --output OUTPUT
                               [--angle-source {raw,vision,fused}]

Prepare a new evidence-bound development training profile; offline only.

options:
  -h, --help            show this help message and exit
  --repo REPO           Repository containing the preserved source profiles
                        and evidence.
  --output OUTPUT
  --angle-source {raw,vision,fused}
```

## scripts/prepare-training-model

```text
usage: prepare_passive_training.py [-h] --freeze FREEZE --executor-parameters
                                   EXECUTOR_PARAMETERS --observation-config
                                   OBSERVATION_CONFIG --assumptions
                                   ASSUMPTIONS --output OUTPUT

Prepare immutable Gym/PPO inputs from a frozen passive candidate; no rig
access.

options:
  -h, --help            show this help message and exit
  --freeze FREEZE
  --executor-parameters EXECUTOR_PARAMETERS
  --observation-config OBSERVATION_CONFIG
  --assumptions ASSUMPTIONS
  --output OUTPUT
```

## scripts/rl-diagnostics

```text
usage: rl_diagnostics.py [-h] {pilot,summarize} ...

Short offline PPO experiments and summaries; never connect to a rig or Colab.

positional arguments:
  {pilot,summarize}

options:
  -h, --help         show this help message and exit
```

## scripts/rl-diagnostics pilot

```text
usage: rl_diagnostics.py pilot [-h] --profile PROFILE --output OUTPUT
                               --variant
                               {mixed,upright,upright-scaled,upright-lowstd}
                               --seed SEED [--steps STEPS] [--every EVERY]
                               [--seconds SECONDS]
                               [--evaluation-seconds EVALUATION_SECONDS]
                               [--evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]]

options:
  -h, --help            show this help message and exit
  --profile PROFILE
  --output OUTPUT
  --variant {mixed,upright,upright-scaled,upright-lowstd}
  --seed SEED
  --steps STEPS
  --every EVERY
  --seconds SECONDS
  --evaluation-seconds EVALUATION_SECONDS
  --evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]
```

## scripts/rl-diagnostics summarize

```text
usage: rl_diagnostics.py summarize [-h] --output OUTPUT pilots [pilots ...]

positional arguments:
  pilots

options:
  -h, --help       show this help message and exit
  --output OUTPUT
```

## scripts/robust-swing-learning

```text
usage: robust_swing.py [-h] --profile PROFILE --output OUTPUT --warm-run
                       WARM_RUN --warm-parity WARM_PARITY --seed SEED
                       [--randomized] [--bias-degrees BIAS_DEGREES]
                       [--observer-bw {6,8,10}] [--steps STEPS]
                       [--every EVERY] [--seconds SECONDS]
                       [--evaluation-seconds EVALUATION_SECONDS]
                       [--training-seeds TRAINING_SEEDS [TRAINING_SEEDS ...]]
                       [--evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]]
                       [--heldout-seeds HELDOUT_SEEDS [HELDOUT_SEEDS ...]]
                       [--learning-rate LEARNING_RATE]
                       [--policy-std POLICY_STD]

Offline full-task actor transfer and matched engineering randomization.
Transfers numeric actor weights only. Critic, optimizer and exploration are
fresh; old-profile performance does not certify the new experiment. No
hardware API or actor export is provided. All physics and reward assumptions
remain explicit.

options:
  -h, --help            show this help message and exit
  --profile PROFILE
  --output OUTPUT
  --warm-run WARM_RUN
  --warm-parity WARM_PARITY
  --seed SEED
  --randomized
  --bias-degrees BIAS_DEGREES
  --observer-bw {6,8,10}
                        Override the profile observer bandwidth (Hz).
  --steps STEPS
  --every EVERY
  --seconds SECONDS
  --evaluation-seconds EVALUATION_SECONDS
  --training-seeds TRAINING_SEEDS [TRAINING_SEEDS ...]
  --evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]
  --heldout-seeds HELDOUT_SEEDS [HELDOUT_SEEDS ...]
  --learning-rate LEARNING_RATE
  --policy-std POLICY_STD
```

## scripts/run-balance-policy

```text
usage: balance_hardware.py [-h] --actor ACTOR --port PORT
                           --expected-upright-raw EXPECTED_UPRIGHT_RAW
                           [--development-only] [--execute]
                           [--guard-profile {commissioning,rig}]
                           [--start-mode {upright,hanging}]
                           [--duration DURATION]
                           [--max-acceleration MAX_ACCELERATION]
                           [--inference-backend {numpy,python}]
                           [--preflight-seconds PREFLIGHT_SECONDS]
                           [--log-dir LOG_DIR] [--no-vision-telemetry]

Bounded, development-only learned control through the normal SDK runner. The
default requires an already homed, stopped rig and a prepared upright start.
Explicit hanging admission permits a swing-up/balance actor with the rig
profile. It never recenters, clears faults, writes parameters or changes
calibration. Limits apply to observed state, not independently measured truth;
STOP/lease expiry is not a model of physical stopping distance.

options:
  -h, --help            show this help message and exit
  --actor ACTOR         Validated numeric actor.json; never a Torch
                        checkpoint.
  --port PORT           Explicit serial device path.
  --expected-upright-raw EXPECTED_UPRIGHT_RAW
                        Previously verified saved encoder reference count,
                        0..4095. Does not calibrate the rig.
  --development-only    Acknowledge unqualified development inference.
  --execute             Explicitly arm; omitted means stopped shadow only.
  --guard-profile {commissioning,rig}
                        commissioning: narrow balance envelope; rig: native
                        rail/speed bounds.
  --start-mode {upright,hanging}
                        hanging permits a swing-up/balance actor; requires
                        --guard-profile rig. Does not calibrate.
  --duration DURATION   Requested duration, .001..10 seconds for commissioning
                        or .001..60 for rig (default 1).
  --max-acceleration MAX_ACCELERATION
                        Raw demand ceiling in m/s², at most 25. Excess faults;
                        no clipping (default .25).
  --inference-backend {numpy,python}
                        Warmed NumPy contraction by default; python is the
                        scalar parity/debug path.
  --preflight-seconds PREFLIGHT_SECONDS
                        Stopped sensor acquisition deadline.
  --log-dir LOG_DIR     SDK JSONL trace directory.
  --no-vision-telemetry
                        Disable the read-only loopback encoder mirror (default
                        UDP port 3096).
```

## scripts/run-neural-policy

```text
usage: run_neural_policy.py [-h] --actor ACTOR --port PORT
                            [--development-only] [--execute]
                            [--duration DURATION]
                            [--max-acceleration MAX_ACCELERATION]
                            [--sensing-config SENSING_CONFIG]
                            [--preflight-seconds PREFLIGHT_SECONDS]
                            [--log-dir LOG_DIR]

Run a numeric SDK actor in shadow, or explicitly execute development actions.

options:
  -h, --help            show this help message and exit
  --actor ACTOR         Exported actor.json; never a Torch/pickle checkpoint.
  --port PORT           Explicit serial device path.
  --development-only    Acknowledge unqualified development actor; does not
                        grant hardware acceptance.
  --execute             Explicitly arm and submit actions; omitted means
                        stopped shadow inference.
  --duration DURATION   Bounded run duration in seconds.
  --max-acceleration MAX_ACCELERATION
                        Executed raw acceleration ceiling in m/s²; excess
                        demands fault instead of clipping.
  --sensing-config SENSING_CONFIG
                        Required explicit camera calibration, angular
                        alignment and current clock binding for vision/fused
                        actors.
  --preflight-seconds PREFLIGHT_SECONDS
                        Stopped causal sensor warmup deadline.
  --log-dir LOG_DIR     Optional SDK JSONL trace directory.
```

## scripts/swing-learning

```text
usage: swing_learning.py [-h] {train,evaluate} ...

Local observed-state swing-up and balance training; no hardware commands.

positional arguments:
  {train,evaluate}

options:
  -h, --help        show this help message and exit
```

## scripts/swing-learning train

```text
usage: swing_learning.py train [-h] --profile PROFILE --output OUTPUT
                               --initialization
                               {scratch,balance,demonstrations} --seed SEED
                               [--steps STEPS] [--every EVERY]
                               [--reset-mode {mixed,curriculum}]
                               [--seconds SECONDS]
                               [--learning-rate LEARNING_RATE]
                               [--policy-std POLICY_STD]
                               [--evaluation-seconds EVALUATION_SECONDS]
                               [--evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]]
                               [--demonstrations DEMONSTRATIONS]
                               [--train-episodes TRAIN_EPISODES [TRAIN_EPISODES ...]]
                               [--validation-episodes VALIDATION_EPISODES [VALIDATION_EPISODES ...]]
                               [--imitation-updates IMITATION_UPDATES]
                               [--balance-anchor-weight BALANCE_ANCHOR_WEIGHT]

options:
  -h, --help            show this help message and exit
  --profile PROFILE
  --output OUTPUT
  --initialization {scratch,balance,demonstrations}
  --seed SEED
  --steps STEPS
  --every EVERY
  --reset-mode {mixed,curriculum}
  --seconds SECONDS
  --learning-rate LEARNING_RATE
  --policy-std POLICY_STD
  --evaluation-seconds EVALUATION_SECONDS
  --evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]
  --demonstrations DEMONSTRATIONS
  --train-episodes TRAIN_EPISODES [TRAIN_EPISODES ...]
  --validation-episodes VALIDATION_EPISODES [VALIDATION_EPISODES ...]
  --imitation-updates IMITATION_UPDATES
  --balance-anchor-weight BALANCE_ANCHOR_WEIGHT
```

## scripts/swing-learning evaluate

```text
usage: swing_learning.py evaluate [-h] --output OUTPUT --seeds SEEDS
                                  [SEEDS ...] [--seconds SECONDS]
                                  [--checkpoint CHECKPOINT]
                                  [--starts {hanging,upright} [{hanging,upright} ...]]
                                  run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --output OUTPUT
  --seeds SEEDS [SEEDS ...]
  --seconds SECONDS
  --checkpoint CHECKPOINT
  --starts {hanging,upright} [{hanging,upright} ...]
```

## scripts/system-id

```text
usage: cli.py [-h]
              {inspect,collect-passive,collect-pulse,recover-passive,review-recording,review-releases,review-fit,annotations-template,fit-passive,fit-driven,assumptions-template,export-model,gym-smoke}
              ...

Operator procedures for immutable collection, fitting and scoped simulation.

positional arguments:
  {inspect,collect-passive,collect-pulse,recover-passive,review-recording,review-releases,review-fit,annotations-template,fit-passive,fit-driven,assumptions-template,export-model,gym-smoke}
    inspect             Read saved reference, home, health and live parameters
                        in a stopped session.
    collect-passive     Record operator-released oscillations with the motor
                        disabled; physically restrain the cart.
    collect-pulse       Execute one allowlisted cart pulse then12s feedback
                        hold; requires --execute.
    recover-passive     Explicitly review a passive KeyboardInterrupt and
                        preserve a separate recovery decision; never rewrite
                        raw evidence.
    review-recording    Check completed raw data and plot observations without
                        fitting or selecting intervals.
    review-releases     Compare raw camera/encoder relative hanging and
                        qualify explicitly annotated release poses; no
                        fitting.
    review-fit          Plot frozen passive-fit predictions on the exact
                        validation data; never refit or change acceptance.
    annotations-template
                        Create an explicit manual free-release annotation
                        template; never select fit windows automatically.
    fit-passive         Fit training-only passive dynamics and score
                        independently annotated validation releases.
    fit-driven          Run the existing strict driven pendulum fitter using
                        raw theta and MCU acceleration.
    assumptions-template
                        Create an editable complete provisional simulation
                        configuration at100Hz; values remain assumptions.
    export-model        Export an accepted scoped fit with explicit
                        assumptions; unsupported dynamics fail closed.
    gym-smoke           Load an exported model and run a bounded headless
                        zero-action check; no hardware/RL claim.

options:
  -h, --help            show this help message and exit

Help and offline commands never open serial. See docs/system-identification-
workflow.md for purpose, annotations and model limits.
```

## scripts/system-id inspect

```text
usage: cli.py inspect [-h] --port PORT --output OUTPUT
                      [--expected-reference EXPECTED_REFERENCE]
                      [--expected-home EXPECTED_HOME]

Read saved reference, home, health and live parameters in a stopped session.

options:
  -h, --help            show this help message and exit
  --port PORT           Explicit serial device; no discovery, home, clear or
                        calibration.
  --output OUTPUT       New immutable run directory, including failure
                        evidence.
  --expected-reference EXPECTED_REFERENCE
                        Optional exact saved upright raw encoder reference.
  --expected-home EXPECTED_HOME
                        Optional exact current home epoch.
```

## scripts/system-id collect-passive

```text
usage: cli.py collect-passive [-h] --port PORT --output OUTPUT
                              [--expected-reference EXPECTED_REFERENCE]
                              [--expected-home EXPECTED_HOME]
                              [--dataset-role {training,validation,development}]
                              [--run-label RUN_LABEL]
                              [--camera-url CAMERA_URL | --no-camera]
                              [--seconds SECONDS]
                              [--release-angles-deg RELEASE_ANGLES_DEG [RELEASE_ANGLES_DEG ...]]
                              [--release-directions {left,right} [{left,right} ...]]
                              [--repetitions REPETITIONS]
                              [--cart-restraint CART_RESTRAINT]

Record operator-released oscillations with the motor disabled; physically
restrain the cart.

options:
  -h, --help            show this help message and exit
  --port PORT           Explicit serial device; no discovery, home, clear or
                        calibration.
  --output OUTPUT       New immutable run directory, including failure
                        evidence.
  --expected-reference EXPECTED_REFERENCE
                        Optional exact saved upright raw encoder reference.
  --expected-home EXPECTED_HOME
                        Optional exact current home epoch.
  --dataset-role {training,validation,development}
  --run-label RUN_LABEL
                        Descriptive immutable recording label.
  --camera-url CAMERA_URL
                        Raw sensing-stream URL; must become ready before
                        serial collection.
  --no-camera           Pulse only: explicitly record missing independent
                        camera evidence; passive collection requires camera.
  --seconds SECONDS     Maximum recording duration, 1..180s; type done then
                        Enter to finish early after recording begins.
  --release-angles-deg RELEASE_ANGLES_DEG [RELEASE_ANGLES_DEG ...]
                        Requested degrees away from hanging; labels are not
                        measured angles.
  --release-directions {left,right} [{left,right} ...]
                        Directions in camera view.
  --repetitions REPETITIONS
  --cart-restraint CART_RESTRAINT
                        How you will keep the cart fixed; required with
                        requested angles.
```

## scripts/system-id collect-pulse

```text
usage: cli.py collect-pulse [-h] --port PORT --output OUTPUT
                            [--expected-reference EXPECTED_REFERENCE]
                            [--expected-home EXPECTED_HOME]
                            [--dataset-role {training,validation,development}]
                            [--run-label RUN_LABEL]
                            [--camera-url CAMERA_URL | --no-camera]
                            [--pulse-seconds {0.45,0.65,0.8,1.0}]
                            [--hold-seconds HOLD_SECONDS] [--execute]
                            --amplitude-mm {-30,-20,-10,-5,5,10,20,30}

Execute one allowlisted cart pulse then12s feedback hold; requires --execute.

options:
  -h, --help            show this help message and exit
  --port PORT           Explicit serial device; no discovery, home, clear or
                        calibration.
  --output OUTPUT       New immutable run directory, including failure
                        evidence.
  --expected-reference EXPECTED_REFERENCE
                        Optional exact saved upright raw encoder reference.
  --expected-home EXPECTED_HOME
                        Optional exact current home epoch.
  --dataset-role {training,validation,development}
  --run-label RUN_LABEL
                        Descriptive immutable recording label.
  --camera-url CAMERA_URL
                        Raw sensing-stream URL; must become ready before
                        serial collection.
  --no-camera           Pulse only: explicitly record missing independent
                        camera evidence; passive collection requires camera.
  --pulse-seconds {0.45,0.65,0.8,1.0}
                        Pulse duration; unsafe amplitude/duration pairs fail
                        before serial. Default0.65s.
  --hold-seconds HOLD_SECONDS
                        Explicit3..12s active cart feedback hold,
                        default12s;20ms leases are unchanged.
  --execute             Authorize this invocation to issue ARM and
                        acceleration requests.
  --amplitude-mm {-30,-20,-10,-5,5,10,20,30}
                        Signed pulse amplitude; begin with5mm and inspect
                        before escalating.
```

## scripts/system-id recover-passive

```text
usage: cli.py recover-passive [-h] --input INPUT --reason REASON

options:
  -h, --help       show this help message and exit
  --input INPUT    Local Rig JSONL or JSONL.gz with its original sibling
                   reports and camera evidence.
  --reason REASON  Why the operator interrupted this passive recording;
                   required for the recovery audit.
```

## scripts/system-id review-recording

```text
usage: cli.py review-recording [-h] --input INPUT --output OUTPUT

options:
  -h, --help       show this help message and exit
  --input INPUT
  --output OUTPUT
```

## scripts/system-id review-releases

```text
usage: cli.py review-releases [-h] --input INPUT --annotations ANNOTATIONS
                              --output OUTPUT

options:
  -h, --help            show this help message and exit
  --input INPUT
  --annotations ANNOTATIONS
  --output OUTPUT
```

## scripts/system-id review-fit

```text
usage: cli.py review-fit [-h] --fit FIT --validation VALIDATION
                         --validation-annotations VALIDATION_ANNOTATIONS
                         --output OUTPUT

options:
  -h, --help            show this help message and exit
  --fit FIT
  --validation VALIDATION
  --validation-annotations VALIDATION_ANNOTATIONS
  --output OUTPUT
```

## scripts/system-id annotations-template

```text
usage: cli.py annotations-template [-h] --input INPUT --output OUTPUT

options:
  -h, --help       show this help message and exit
  --input INPUT    Rig JSONL, JSONL.gz, or archive.tar.gz::exact/member.jsonl
  --output OUTPUT
```

## scripts/system-id fit-passive

```text
usage: cli.py fit-passive [-h] --training TRAINING --training-annotations
                          TRAINING_ANNOTATIONS --validation VALIDATION
                          --validation-annotations VALIDATION_ANNOTATIONS
                          [--model {viscous,viscous_coulomb}] --output OUTPUT

options:
  -h, --help            show this help message and exit
  --training TRAINING
  --training-annotations TRAINING_ANNOTATIONS
  --validation VALIDATION
  --validation-annotations VALIDATION_ANNOTATIONS
  --model {viscous,viscous_coulomb}
                        Declare before examining validation; never select the
                        winner from validation.
  --output OUTPUT
```

## scripts/system-id fit-driven

```text
usage: cli.py fit-driven [-h] --training TRAINING --validation VALIDATION
                         --output OUTPUT

options:
  -h, --help            show this help message and exit
  --training TRAINING
  --validation VALIDATION
  --output OUTPUT
```

## scripts/system-id assumptions-template

```text
usage: cli.py assumptions-template [-h] --output OUTPUT

options:
  -h, --help       show this help message and exit
  --output OUTPUT
```

## scripts/system-id export-model

```text
usage: cli.py export-model [-h] --report REPORT --scope {passive-down,driven}
                           --assumptions ASSUMPTIONS --output OUTPUT

options:
  -h, --help            show this help message and exit
  --report REPORT
  --scope {passive-down,driven}
  --assumptions ASSUMPTIONS
  --output OUTPUT
```

## scripts/system-id gym-smoke

```text
usage: cli.py gym-smoke [-h] --model MODEL [--steps STEPS] --output OUTPUT

options:
  -h, --help       show this help message and exit
  --model MODEL
  --steps STEPS
  --output OUTPUT
```

## scripts/system-id-campaign

```text
usage: campaign_cli.py [-h] {plan,rehearse,collect,review,bundle} ...

Run the remaining system-ID measurements and package raw evidence for
analysis.

positional arguments:
  {plan,rehearse,collect,review,bundle}

options:
  -h, --help            show this help message and exit
```

## scripts/system-id-campaign plan

```text
usage: campaign_cli.py plan [-h]
                            [--suite {autonomous,actuator,timing,coupled,angle-map,capture-friction,cart-map}]
                            [--level {gentle,standard}]
                            [--repetitions REPETITIONS] [--seconds SECONDS]

options:
  -h, --help            show this help message and exit
  --suite {autonomous,actuator,timing,coupled,angle-map,capture-friction,cart-map}
  --level {gentle,standard}
  --repetitions REPETITIONS
                        1..5 repeated powered suites; manual suites have their
                        own paired repetitions.
  --seconds SECONDS     5..25 seconds for each timing/coupled trial.
```

## scripts/system-id-campaign rehearse

```text
usage: campaign_cli.py rehearse [-h]
                                [--suite {autonomous,actuator,timing,coupled,angle-map,capture-friction,cart-map}]
                                [--level {gentle,standard}]
                                [--repetitions REPETITIONS]
                                [--seconds SECONDS] --output OUTPUT

options:
  -h, --help            show this help message and exit
  --suite {autonomous,actuator,timing,coupled,angle-map,capture-friction,cart-map}
  --level {gentle,standard}
  --repetitions REPETITIONS
                        1..5 repeated powered suites; manual suites have their
                        own paired repetitions.
  --seconds SECONDS     5..25 seconds for each timing/coupled trial.
  --output OUTPUT       New directory; never overwrite evidence.
```

## scripts/system-id-campaign collect

```text
usage: campaign_cli.py collect [-h]
                               [--suite {autonomous,actuator,timing,coupled,angle-map,capture-friction,cart-map}]
                               [--level {gentle,standard}]
                               [--repetitions REPETITIONS] [--seconds SECONDS]
                               --output OUTPUT --port PORT [--encoder-only]
                               [--execute] [--camera-url CAMERA_URL]
                               [--dataset-role {training,validation,development}]
                               [--run-label RUN_LABEL]
                               [--cart-restraint CART_RESTRAINT]
                               [--manual-timeout-s MANUAL_TIMEOUT_S]
                               [--expected-reference EXPECTED_REFERENCE]
                               [--expected-home EXPECTED_HOME]

options:
  -h, --help            show this help message and exit
  --suite {autonomous,actuator,timing,coupled,angle-map,capture-friction,cart-map}
  --level {gentle,standard}
  --repetitions REPETITIONS
                        1..5 repeated powered suites; manual suites have their
                        own paired repetitions.
  --seconds SECONDS     5..25 seconds for each timing/coupled trial.
  --output OUTPUT       New directory; never overwrite evidence.
  --port PORT
  --encoder-only        Powered suites only: explicitly omit camera; no
                        independent physical cart measurement or actuator
                        calibration.
  --execute             Authorize guarded motion AND return to the saved home.
                        Required for powered suites.
  --camera-url CAMERA_URL
  --dataset-role {training,validation,development}
  --run-label RUN_LABEL
  --cart-restraint CART_RESTRAINT
                        Required for disabled manual suites; state how
                        physical cart position is controlled.
  --manual-timeout-s MANUAL_TIMEOUT_S
  --expected-reference EXPECTED_REFERENCE
  --expected-home EXPECTED_HOME
```

## scripts/system-id-campaign review

```text
usage: campaign_cli.py review [-h] --input INPUT --output OUTPUT

options:
  -h, --help       show this help message and exit
  --input INPUT
  --output OUTPUT
```

## scripts/system-id-campaign bundle

```text
usage: campaign_cli.py bundle [-h] --input INPUT --output OUTPUT

options:
  -h, --help       show this help message and exit
  --input INPUT
  --output OUTPUT
```

## scripts/train-ppo

```text
usage: train_ppo.py [-h] {train,evaluate} ...

Train/resume/evaluate a model-bound PPO actor offline; no rig access.

positional arguments:
  {train,evaluate}
    train           Train PPO and save resumable checkpoint plus numeric SDK
                    actor.
    evaluate        Frozen deterministic evaluation on disjoint seeds.

options:
  -h, --help        show this help message and exit
```

## scripts/train-ppo train

```text
usage: train_ppo.py train [-h] --model MODEL --executor-parameters
                          EXECUTOR_PARAMETERS --observation-config
                          OBSERVATION_CONFIG --prior-parameters
                          PRIOR_PARAMETERS --output OUTPUT
                          [--development-only]
                          [--training-seeds TRAINING_SEEDS [TRAINING_SEEDS ...]]
                          --seed SEED --steps STEPS [--seconds SECONDS]
                          [--n-steps N_STEPS] [--batch-size BATCH_SIZE]
                          [--epochs EPOCHS] [--gamma GAMMA]
                          [--gae-lambda GAE_LAMBDA]
                          [--learning-rate LEARNING_RATE]
                          [--reward-scale REWARD_SCALE]
                          [--randomize | --randomization RANDOMIZATION]
                          [--checkpoint-every CHECKPOINT_EVERY]
                          [--resume RESUME]

options:
  -h, --help            show this help message and exit
  --model MODEL
  --executor-parameters EXECUTOR_PARAMETERS
  --observation-config OBSERVATION_CONFIG
  --prior-parameters PRIOR_PARAMETERS
  --output OUTPUT
  --development-only    Conspicuously admit unqualified simulation work; never
                        accepts a rejected fit.
  --training-seeds TRAINING_SEEDS [TRAINING_SEEDS ...]
                        Explicit seed pool; defaults to 128 seeds, 10000
                        through 10127.
  --seed SEED
  --steps STEPS
  --seconds SECONDS
  --n-steps N_STEPS
  --batch-size BATCH_SIZE
  --epochs EPOCHS
  --gamma GAMMA         100 Hz discount; .999 has approximately a 10 second
                        horizon.
  --gae-lambda GAE_LAMBDA
  --learning-rate LEARNING_RATE
  --reward-scale REWARD_SCALE
                        Positive optimizer reward scale; benchmark score
                        remains unscaled.
  --randomize           Use declared bounded engineering robustness ranges,
                        not fitted uncertainty.
  --randomization RANDOMIZATION
                        Explicit cartpole-training-randomization-v1 JSON;
                        omitted means nominal training.
  --checkpoint-every CHECKPOINT_EVERY
  --resume RESUME
```

## scripts/train-ppo evaluate

```text
usage: train_ppo.py evaluate [-h] --seeds SEEDS [SEEDS ...] --output OUTPUT
                             [--hold-seconds HOLD_SECONDS]
                             run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --seeds SEEDS [SEEDS ...]
  --output OUTPUT
  --hold-seconds HOLD_SECONDS
                        Additional sustained-balance metric; original one-
                        second benchmark is retained.
```

## cartpole-portal-dev

```text
usage: cartpole-portal-dev [-h] [--root ROOT] [--port PORT]

Persistent, loopback-only source-policy preview. Never starts a worker.

options:
  -h, --help   show this help message and exit
  --root ROOT
  --port PORT
```

## cartpole-collect

```text
usage: cartpole-collect [-h] [--url URL] [--streams STREAMS]
                        [--duration DURATION] [--max-hz MAX_HZ]
                        [--limit LIMIT] [--max-records MAX_RECORDS]
                        [--max-bytes MAX_BYTES] [--cursors CURSORS]
                        [--output OUTPUT] [--legacy-sensing]

Bounded read-only NDJSON collection; no hardware commands or clock rewriting.

options:
  -h, --help            show this help message and exit
  --url URL
  --streams STREAMS     comma-separated catalog channel ids
  --duration DURATION
  --max-hz MAX_HZ
  --limit LIMIT
  --max-records MAX_RECORDS
  --max-bytes MAX_BYTES
  --cursors CURSORS     JSON cursor map copied from a previous envelope
  --output OUTPUT       - for stdout; otherwise creates a NEW JSONL file
  --legacy-sensing      export unchanged v1 vision+encoder envelopes from an
                        existing service; SDK shadow is not included
```

## Portal workspace follow-up arguments

Captured from current source; these supersede earlier portal/worker help blocks.

### Portal API

```text
usage: portal.py [-h] --root ROOT --credentials CREDENTIALS [--host HOST]
                 [--port PORT] [--origin ORIGIN] [--camera-url CAMERA_URL]
                 [--enable-reservations] [--rig-id RIG_ID]

Bounded loopback-first HTTP API; browser credentials never appear in URLs.

options:
  -h, --help            show this help message and exit
  --root ROOT
  --credentials CREDENTIALS
  --host HOST
  --port PORT
  --origin ORIGIN
  --camera-url CAMERA_URL
                        read-only camera origin for browser preview
  --enable-reservations
  --rig-id RIG_ID
```

### Portal worker

```text
usage: portal_worker.py [-h] (--local-root LOCAL_ROOT | --portal PORTAL)
                        [--token-file TOKEN_FILE] [--worker WORKER] --rig-id
                        RIG_ID [--backend {simulation,hardware}] [--port PORT]
                        [--rate {100,250,500,1000}] [--log-dir LOG_DIR]
                        [--once] [--spool-root SPOOL_ROOT]
                        [--enable-reservations] [--sensing-url SENSING_URL]
                        [--recording-root RECORDING_ROOT]
                        [--max-acceleration MAX_ACCELERATION]

Trusted outbound pull worker. Uploaded modules are never imported here.

options:
  -h, --help            show this help message and exit
  --local-root LOCAL_ROOT
  --portal PORTAL
  --token-file TOKEN_FILE
  --worker WORKER
  --rig-id RIG_ID
  --backend {simulation,hardware}
  --port PORT
  --rate {100,250,500,1000}
  --log-dir LOG_DIR
  --once
  --spool-root SPOOL_ROOT
  --enable-reservations
                        enable reservation gating for a local queue
  --sensing-url SENSING_URL
                        optional trusted developer-stream service origin to
                        record independently
  --recording-root RECORDING_ROOT
                        persistent run spool; defaults local queue recording-
                        spool or runs/portal-recordings
  --max-acceleration MAX_ACCELERATION
                        trusted ceiling (0,25] m/s²; defaults simulation25,
                        hardware0.25
```

### Local preview

```text
usage: dev.py [-h] [--root ROOT] [--port PORT]

Persistent, loopback-only source-policy preview. Never starts a worker.

options:
  -h, --help   show this help message and exit
  --root ROOT
  --port PORT
```

### AUTO diagnostic replay

```text
usage: feedback_diagnostics.py replay [-h] [--tolerance TOLERANCE] jsonl

positional arguments:
  jsonl

options:
  -h, --help            show this help message and exit
  --tolerance TOLERANCE
```

### AUTO diagnostic surrogate

```text
usage: feedback_diagnostics.py simulate [-h] --parameters PARAMETERS
                                        [--controller {python,native_reference}]
                                        [--rate-hz {100,250}]
                                        [--duration-s DURATION_S]
                                        [--theta THETA] [--omega OMEGA]
                                        [--x X]
                                        [--angular-damping-per-s ANGULAR_DAMPING_PER_S]
                                        [--observer-angle OBSERVER_ANGLE]
                                        [--observer-rate OBSERVER_RATE]
                                        [--reset-observer]

options:
  -h, --help            show this help message and exit
  --parameters PARAMETERS
                        JSON object of ControllerParameters values
  --controller {python,native_reference}
  --rate-hz {100,250}
  --duration-s DURATION_S
  --theta THETA
  --omega OMEGA
  --x X
  --angular-damping-per-s ANGULAR_DAMPING_PER_S
  --observer-angle OBSERVER_ANGLE
  --observer-rate OBSERVER_RATE
  --reset-observer
```

## October 26 developer commands

Generated from the implemented CLI help. These commands do not connect to the rig.

### Portable controller simulation/replay

```text
usage: run.py [-h] [--policy POLICY] --output OUTPUT [--recording RECORDING]
              [--seconds SECONDS] [--seed SEED]
              {simulate,replay}

Offline local trusted-code runner. The portal separately isolates uploaded
code.

positional arguments:
  {simulate,replay}

options:
  -h, --help            show this help message and exit
  --policy POLICY
  --output OUTPUT
  --recording RECORDING
  --seconds SECONDS
  --seed SEED
```

### Run bundle export

```text
usage: dataset.py [-h] --output OUTPUT [--sha256 EXPECTED_SHA256]
                  [--expected-period-ns EXPECTED_PERIOD_NS]
                  bundle

Offline bundle export: preserve provenance; never synthesize rewards or
motion. ZIP members are read with strict bounds, never extracted. Replay
deduplicates identical latest-state snapshots; the original telemetry remains
available.

positional arguments:
  bundle

options:
  -h, --help            show this help message and exit
  --output OUTPUT
  --sha256 EXPECTED_SHA256
  --expected-period-ns EXPECTED_PERIOD_NS
```

### PPO training and numeric export

```text
usage: controlled_training.py [-h]
                              [--objective {controlled-swing-v1,controlled-swing-v2,controlled-swing-v3}]
                              --output OUTPUT [--steps STEPS]
                              [--checkpoint-every CHECKPOINT_EVERY]
                              [--seconds SECONDS] [--seed SEED]
                              [--init-actor INIT_ACTOR] [--resume RESUME]
                              [--profile PROFILE_ID]
                              [--evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]]
                              [--nominal-training]

Offline projected PPO experiment with immutable checkpoints and numeric
export.

options:
  -h, --help            show this help message and exit
  --objective {controlled-swing-v1,controlled-swing-v2,controlled-swing-v3}
  --output OUTPUT
  --steps STEPS
  --checkpoint-every CHECKPOINT_EVERY
  --seconds SECONDS
  --seed SEED
  --init-actor INIT_ACTOR
  --resume RESUME       Trusted checkpoint directory; additional step budget,
                        new output
  --profile PROFILE_ID
  --evaluation-seeds EVALUATION_SEEDS [EVALUATION_SEEDS ...]
  --nominal-training
```

### Prepare a frozen Colab training bundle

```text
usage: controlled_cloud.py [-h] --output OUTPUT [--steps STEPS]
                           [--checkpoint-every CHECKPOINT_EVERY]

Prepare a controlled-swing Colab bundle offline. Never allocate a runtime.

options:
  -h, --help            show this help message and exit
  --output OUTPUT
  --steps STEPS
  --checkpoint-every CHECKPOINT_EVERY
```

### HTTP-only checkpoint backups

```text
usage: controlled_watch.py [-h] --session SESSION --output OUTPUT --cli CLI
                           --cli-pins CLI_PINS [--state-file STATE_FILE]
                           [--max-seconds MAX_SECONDS] [--interval INTERVAL]
                           bundle

Bounded HTTP-only checkpoint backup. No kernel execution or VM lifecycle APIs.

positional arguments:
  bundle

options:
  -h, --help            show this help message and exit
  --session SESSION
  --output OUTPUT
  --cli CLI
  --cli-pins CLI_PINS
  --state-file STATE_FILE
  --max-seconds MAX_SECONDS
  --interval INTERVAL
```

### Explicit starter submission

```text
usage: submit.py [-h] [--artifact ARTIFACT]
                 [--source {simulation,magnetic-step}] [--seconds SECONDS]
                 --key KEY [--reservation-id RESERVATION_ID]
                 [--recording {standard,detailed}] [--collect COLLECT]
                 [--timeout TIMEOUT]

Explicit authenticated submission; physical jobs still require operator
approval.

options:
  -h, --help            show this help message and exit
  --artifact ARTIFACT
  --source {simulation,magnetic-step}
  --seconds SECONDS
  --key KEY             Stable idempotency key for this exact request
  --reservation-id RESERVATION_ID
  --recording {standard,detailed}
  --collect COLLECT     Wait for run and verified bundle; destination must be
                        new
  --timeout TIMEOUT
```
