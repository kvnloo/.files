module.exports = {
  config: {
    // default font size in pixels for all tabs
    fontSize: 14,

    // font family with optional fallbacks
    fontFamily: '"Roboto Mono for Powerline", "Input Mono", "Menlo", "DejaVu Sans Mono", "Lucida Console", "monospace"',

    // `BEAM` for |, `UNDERLINE` for _, `BLOCK` for █
    cursorShape: 'BLOCK',


    // terminal background color
    backgroundColor: '#293340',

    // color of the text
    foregroundColor: '#CDD2E9',

    // terminal cursor background color and opacity (hex, rgb, hsl, hsv, hwb or cmyk)
    cursorColor: 'rgba(192,177,139,0.60)',

    // border color (window, tabs)
    borderColor: '#323E4D',

    // custom css to embed in the main window
    css: '',

    // custom css to embed in the terminal window
    // termCSS: `
    //   x-screen {
    //     -webkit-font-smoothing: subpixel-antialiased !important;
    //   }
    // `,

    // set to `true` if you're using a Linux set up
    // that doesn't shows native menus
    // default: `false` on Linux, `true` on Windows (ignored on macOS)
    showHamburgerMenu: '',

    // set to `false` if you want to hide the minimize, maximize and close buttons
    // additionally, set to `'left'` if you want them on the left, like in Ubuntu
    // default: `true` on windows and Linux (ignored on macOS)
    showWindowControls: '',

    // custom padding (css format, i.e.: `top right bottom left`)
    padding: '15px 15px',

    // the full list. if you're going to provide the full color palette,
    // including the 6 x 6 color cubes and the grayscale map, just provide
    // an array here instead of a color map object
    colors: {
      black             : '#293340',
      red               : '#E17E85',
      green             : '#61BA86',
      yellow            : '#FFEC8E',
      blue              : '#4CB2FF',
      magenta           : '#BE86E3',
      cyan              : '#2DCED0',
      white             : '#CDD2E9',
      lightBlack        : '#546386',
      lightRed          : '#E17E85',
      lightGreen        : '#61BA86',
      lightYellow       : '#FFB68E',
      lightBlue         : '#4CB2FF',
      lightMagenta      : '#BE86E3',
      lightCyan         : '#2DCED0',
      lightWhite        : '#CDD2E9'
    },

    // the shell to run when spawning a new session (i.e. /usr/local/bin/fish)
    // if left empty, your system's login shell will be used by default
    shell: '/bin/zsh',

    // for setting shell arguments (i.e. for using interactive shellArgs: ['-i'])
    // by default ['--login'] will be used
    shellArgs: ['--login'],

    // for environment variables
    env: {},

    // set to false for no bell
    bell: '~/',

    // if true, selected text will automatically be copied to the clipboard
    copyOnSelect: false

    // URL to custom bell
    // bellSoundURL: 'http://example.com/bell.mp3',

    // for advanced config flags please refer to https://hyper.is/#cfg
  },

  // a list of plugins to fetch and install from npm
  // format: [@org/]project[#version]
  // examples:
  //   `hyperpower`
  //   `@company/project`
  //   `project#1.0.1`
  plugins: [
    'hyperminimal',
    'hyper-chesterish',
    'hyper-statusline',
    'hyper-tabs-enhanced'
  ],

  // in development, you can create a directory under
  // `~/.hyper_plugins/local/` and include it here
  // to load it and avoid it being `npm install`ed
  localPlugins: []
};
