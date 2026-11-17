# CamillaDSP on macOS

The signal path is BlackHole 2ch → CamillaDSP → USB DAC. Install BlackHole 2ch,
SwitchAudioSource and the official CamillaDSP binary before running
`bash config/camilladsp/install.sh` from the repo root.

## Local DAC profiles

Generate profiles outside the checkout to keep device settings local. For a
Topping DX5, run from the repo root:

```sh
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/camilladsp"
bash config/camilladsp/generate-rate-configs.sh "$config_dir/configs-dx5" DX5
ln -sfn "$config_dir/configs-dx5" "$config_dir/configs"
ln -sfn "$PWD/config/camilladsp/experience_helper.py" "$config_dir/experience_helper.py"
ln -sfn "$PWD/config/autoeq" "$config_dir/../autoeq"
cd "$config_dir"
python3 -m venv venv
venv/bin/pip install 'git+https://github.com/HEnquist/pycamilladsp.git' PyYAML
printf 'CURRENT_PROFILE="clean"\nCURRENT_RATE="48000"\n' > .state
"$HOME/.local/bin/camilladsp" -c configs/camilladsp-48000.yml
```

Use the local config directory as CamillaDSP's working directory so the FIR
paths resolve. For launch at login, adapt `com.camilladsp.daemon.plist` to your
home directory and desired startup profile before installing it in
`~/Library/LaunchAgents`. Once CamillaDSP is running and the DAC is available,
select BlackHole 2ch as the default macOS output.

The bundled FIR rates are 44.1, 48, 96, 192 and 384 kHz. Clean, Crossfeed and
Room have configs at each rate. The checkout defaults to the HD800S IRs.

## Following changes to BlackHole's sample rate

Install the [CamillaDSP Controller](https://github.com/HEnquist/camilladsp-controller)
with Python 3.10 or later and CFFI. Run it with its checkout as the working
directory so it can build and import its CoreAudio bindings. Example for Clean:

```sh
python3 controller.py -p 1234 -d 'BlackHole 2ch' -r 48000 \
  -s "${XDG_CONFIG_HOME:-$HOME/.config}/camilladsp/configs/camilladsp-{samplerate}.yml"
```

Use that command in a separate user LaunchAgent to start the controller at login.
The template selects Clean whenever the rate changes. The controller reacts to
the device rate, so Chrome playback follows the rate already selected on
BlackHole. A player or separate integration must set the device rate to match
the source for automatic per-track switching.
