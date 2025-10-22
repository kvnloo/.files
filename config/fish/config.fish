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
