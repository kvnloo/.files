# Path to Oh My Fish install.
set -q XDG_DATA_HOME
  and set -gx OMF_PATH "$XDG_DATA_HOME/omf"
  or set -gx OMF_PATH "$HOME/.local/share/omf"

# Hosts without Oh My Fish must still have quiet noninteractive SSH startup.
if test -r "$OMF_PATH/init.fish"
    source "$OMF_PATH/init.fish"
end
