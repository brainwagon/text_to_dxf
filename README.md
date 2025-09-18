# Text to DXF

A Python script to convert text into DXF vector outlines. This is useful for generating paths for CNC machines, laser cutters, or for use in CAD software.

## Features

*   Converts text to DXF using TrueType (.ttf) and OpenType (.otf) fonts.
*   Supports system-installed fonts and local font files.
*   Adjustable font size, character spacing, and kerning.
*   Lists available system fonts.

## Usage

### Listing available fonts

To see a list of fonts available on your system:

```bash
python text_to_dxf.py --list-fonts
```

### Basic Conversion

To convert a string of text to a DXF file:

```bash
python text_to_dxf.py "Your Text Here" output.dxf
```

This will use the default font (Arial) and settings.

### Specifying a Font

You can specify a system font by name:

```bash
python text_to_dxf.py "Hello World" hello.dxf --font "Times New Roman"
```

Or use a local font file:

```bash
python text_to_dxf.py "Custom Font" custom.dxf --font ./gunplay.ttf
```

### Adjusting Size and Spacing

You can control the font size (in mm) and character spacing:

```bash
python text_to_dxf.py "Sized" sized.dxf --size 50 --spacing 1.5
```

### Controlling Kerning

Kerning is enabled by default to ensure proper character spacing for fonts that support it. You can disable it using the `--no-kerning` flag:

```bash
python text_to_dxf.py "AVATAR" avatar.dxf --font gunplay.ttf --no-kerning
```

### All Options

```
usage: text_to_dxf.py [-h] [--list-fonts] [--font FONT] [--size SIZE]
                      [--spacing SPACING] [--quality {low,medium,high}]
                      [--kerning | --no-kerning] [-v]
                      [text] [output]

Convert text to DXF font outlines

positional arguments:
  text                  Text string to convert
  output                Output DXF file path

options:
  -h, --help            show this help message and exit
  --list-fonts          List all available system fonts and exit
  --font FONT           Font name to use (default: Arial) or path to font file
  --size SIZE           Font size in mm (default: 20)
  --spacing SPACING     Character spacing multiplier (default: 1.2)
  --quality {low,medium,high}
                        Curve quality: low, medium, or high (default: high)
  --kerning, --no-kerning
                        Enable/disable font kerning (default: --kerning)
  -v, --verbose         Enable verbose debug output
```

## Requirements

*   Python 3
*   `fonttools`
*   `ezdxf`
*   `tqdm`

You can install the required libraries using pip:

```bash
pip install fonttools ezdxf tqdm
```