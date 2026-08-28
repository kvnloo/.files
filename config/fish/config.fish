grep -e "^export " ~/.profile | while read e
	set var (echo $e | sed -E "s/^export ([A-Z_]+)=(.*)\$/\1/")
	set value (echo $e | sed -E "s/^export ([A-Z_]+)=(.*)\$/\2/")
	
	# remove surrounding quotes if existing
	set value (echo $value | sed -E "s/^\"(.*)\"\$/\1/")

	if test $var = "PATH"
		# replace ":" by spaces. this is how PATH looks for Fish
		set value (echo $value | sed -E "s/:/ /g")
	
		# use eval because we need to expand the value
		eval set -xg $var $value

		continue
	end

	# evaluate variables. we can use eval because we most likely just used "$var"
	set value (eval echo $value)

	#echo "set -xg '$var' '$value' (via '$e')"
	set -xg $var $value
  end

set -g theme_powerline_fonts no
set -g theme_nerd_fonts yes
set -g theme_color_scheme base16

alias rm='rmtrash'
alias '`kwm`'='brew services restart kwm'

alias '`cdresume`'='cd ~/GoogleDrive/Jobs/resume'
alias '`cdrepos`'='cd ~/Desktop/repos'
alias '`cdprojects`'='cd ~/GoogleDrive/Projects'

# >>> grok installer >>>
fish_add_path $HOME/.grok/bin
# <<< grok installer <<<

function tmuxr --description "Start tmux with a writable socket dir (fixes socket permission failures)"
    set -l socket_file "$HOME/.tmux/repair-socket"
    set -l uid (id -u)
    set -l candidate_dirs \
        /tmp \
        /run/user/$uid \
        (test -n "$XDG_RUNTIME_DIR"; and echo $XDG_RUNTIME_DIR) \
        (test -n "$TMPDIR"; and echo $TMPDIR) \
        $HOME/.tmux

    set -l runtime_dir ""
    for dir in $candidate_dirs
        if test -d "$dir" && test -w "$dir"
            set runtime_dir "$dir"
            break
        end
    end

    if test -z "$runtime_dir"
        echo "tmuxr: no writable runtime directory found (TMUX_TMPDIR not set)" >&2
        return 1
    end

    if test "$runtime_dir" != "$HOME/.tmux"
        set socket_file "$runtime_dir/tmux-repair-socket"
    end

    # Remove stale fixed-session socket so tmux can create a fresh one.
    set -l stale_pattern "$runtime_dir/tmux-repair*"
    for socket in $stale_pattern
        test -S "$socket"
        and command rm -f "$socket"
    end

    if test (count $argv) -gt 0
        env TMUX_TMPDIR="$runtime_dir" XDG_RUNTIME_DIR="$runtime_dir" tmux -S "$socket_file" $argv
    else
        env TMUX_TMPDIR="$runtime_dir" XDG_RUNTIME_DIR="$runtime_dir" tmux -S "$socket_file" new-session
    end
end

alias '`tmuxr`'='tmuxr'
