#!/usr/bin/env python3
"""
Text to DXF Font Outline Generator

This script takes a TrueType font file, a string of text, and generates a DXF file
containing the vector outlines of the text characters, including support for holes
in characters like 'A', 'B', 'O', etc.

Requirements:
    pip install fonttools ezdxf

Usage:
    python text_to_dxf.py "Hello World" font.ttf output.dxf
"""

import sys
import argparse
import platform
import os
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
import ezdxf
from ezdxf.math import Vec2
import math
from tqdm import tqdm
import matplotlib.pyplot as plt


def get_system_font_paths():
    """Get standard font directories for the current operating system."""
    system = platform.system().lower()
    font_paths = []
    
    if system == "windows":
        # Windows font directories
        font_paths.extend([
            os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Fonts'),
        ])
    elif system == "darwin":  # macOS
        # macOS font directories
        font_paths.extend([
            '/System/Library/Fonts',
            '/Library/Fonts',
            os.path.expanduser('~/Library/Fonts'),
        ])
    else:  # Linux and other Unix-like systems
        # Linux font directories
        font_paths.extend([
            '/usr/share/fonts',
            '/usr/local/share/fonts',
            os.path.expanduser('~/.fonts'),
            os.path.expanduser('~/.local/share/fonts'),
        ])
    
    # Filter out non-existent directories
    return [path for path in font_paths if os.path.exists(path)]


def find_all_fonts():
    """Find all TrueType and OpenType fonts on the system."""
    fonts = {}  # Dictionary to store font_name: font_path
    font_extensions = {'.ttf', '.otf', '.ttc'}
    
    for font_dir in get_system_font_paths():
        try:
            for root, dirs, files in os.walk(font_dir):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in font_extensions):
                        font_path = os.path.join(root, file)
                        try:
                            # Try to get the font name from the font file
                            font = TTFont(font_path)
                            name_table = font.get('name')
                            if name_table:
                                # Try to get the font family name (ID 1) and full name (ID 4)
                                family_name = None
                                full_name = None
                                
                                for record in name_table.names:
                                    if record.nameID == 1 and record.platformID == 3:  # Family name, Windows platform
                                        try:
                                            family_name = record.toUnicode()
                                        except:
                                            pass
                                    elif record.nameID == 4 and record.platformID == 3:  # Full name, Windows platform
                                        try:
                                            full_name = record.toUnicode()
                                        except:
                                            pass
                                
                                # Use full name if available, otherwise family name, otherwise filename
                                display_name = full_name or family_name or os.path.splitext(file)[0]
                                fonts[display_name] = font_path
                            else:
                                # Fallback to filename if no name table
                                fonts[os.path.splitext(file)[0]] = font_path
                            
                            font.close()
                        except Exception:
                            # If we can't read the font, use the filename
                            fonts[os.path.splitext(file)[0]] = font_path
        except (PermissionError, OSError):
            # Skip directories we can't access
            continue
    
    return fonts


def list_fonts():
    """List all available fonts on the system."""
    print("Searching for fonts...")
    fonts = find_all_fonts()
    
    if not fonts:
        print("No fonts found on the system.")
        return
    
    print(f"\nFound {len(fonts)} fonts:\n")
    
    # Sort fonts alphabetically
    for font_name in sorted(fonts.keys()):
        font_path = fonts[font_name]
        print(f"  {font_name}")
        print(f"    Path: {font_path}")
        print()




class DXFPen(BasePen):
    """A pen that converts font outlines to DXF polylines."""
    
    def __init__(self, msp, x_offset=0, y_offset=0, scale=1.0, curve_quality=0.5):
        super().__init__(glyphSet=None)
        self.msp = msp  # DXF model space
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.scale = scale
        self.current_path = []
        self.paths = []  # Store all paths for this glyph
        self.curve_quality = curve_quality
        
    def _transform_point(self, pt):
        """Transform point coordinates."""
        x, y = pt
        return (
            (x * self.scale) + self.x_offset,
            (y * self.scale) + self.y_offset
        )
    
    def moveTo(self, pt):
        """Start a new path."""
        if self.current_path:
            self.paths.append(self.current_path)
        self.current_path = [self._transform_point(pt)]
    
    def lineTo(self, pt):
        """Add a line to the current path."""
        self.current_path.append(self._transform_point(pt))
    
    def curveTo(self, *points):
        """Add a cubic Bezier curve to the current path."""
        if not self.current_path:
            return
            
        start = self.current_path[-1]
        cp1, cp2, end = [self._transform_point(pt) for pt in points]
        
        # Calculate curve length to determine appropriate number of segments
        # Rough approximation: sum of control polygon lengths
        dist1 = ((cp1[0] - start[0])**2 + (cp1[1] - start[1])**2)**0.5
        dist2 = ((cp2[0] - cp1[0])**2 + (cp2[1] - cp1[1])**2)**0.5
        dist3 = ((end[0] - cp2[0])**2 + (end[1] - cp2[1])**2)**0.5
        approx_length = dist1 + dist2 + dist3
        
        # Adaptive number of steps based on curve length and scale
        # More segments for longer curves and larger scales
        min_steps = 8
        max_steps = 50
        steps = max(min_steps, min(max_steps, int(approx_length * self.curve_quality)))
        
        # Generate cubic Bezier curve points
        for i in range(1, steps + 1):
            t = i / steps
            # Cubic Bezier formula: B(t) = (1-t)³P₀ + 3(1-t)²tP₁ + 3(1-t)t²P₂ + t³P₃
            t2 = t * t
            t3 = t2 * t
            mt = 1 - t
            mt2 = mt * mt
            mt3 = mt2 * mt
            
            x = mt3 * start[0] + 3 * mt2 * t * cp1[0] + 3 * mt * t2 * cp2[0] + t3 * end[0]
            y = mt3 * start[1] + 3 * mt2 * t * cp1[1] + 3 * mt * t2 * cp2[1] + t3 * end[1]
            self.current_path.append((x, y))
    
    def qCurveTo(self, *points):
        """Add a quadratic Bezier curve to the current path."""
        if not self.current_path:
            return
            
        start = self.current_path[-1]
        
        # Handle quadratic curves (can have multiple control points)
        current_start = start
        for i in range(0, len(points)):
            if i == len(points) - 1:
                # Last point is the end point
                end = self._transform_point(points[i])
                
                # If we only have one point total, it's a line
                if len(points) == 1:
                    self.current_path.append(end)
                else:
                    # Use the previous point as control point
                    if i > 0:
                        cp = self._transform_point(points[i-1])
                    else:
                        # No control point, draw line
                        self.current_path.append(end)
                        break
                    
                    # Calculate curve length for adaptive segmentation
                    dist1 = ((cp[0] - current_start[0])**2 + (cp[1] - current_start[1])**2)**0.5
                    dist2 = ((end[0] - cp[0])**2 + (end[1] - cp[1])**2)**0.5
                    approx_length = dist1 + dist2
                    
                    # Adaptive steps
                    min_steps = 6
                    max_steps = 30
                    steps = max(min_steps, min(max_steps, int(approx_length * self.curve_quality)))
                    
                    # Generate quadratic Bezier curve points
                    for j in range(1, steps + 1):
                        t = j / steps
                        # Quadratic Bezier formula: B(t) = (1-t)²P₀ + 2(1-t)tP₁ + t²P₂
                        mt = 1 - t
                        mt2 = mt * mt
                        t2 = t * t
                        
                        x = mt2 * current_start[0] + 2 * mt * t * cp[0] + t2 * end[0]
                        y = mt2 * current_start[1] + 2 * mt * t * cp[1] + t2 * end[1]
                        self.current_path.append((x, y))
                    
                current_start = end
            else:
                # Handle multiple control points in TrueType quadratic curves
                if i < len(points) - 1:
                    cp1 = self._transform_point(points[i])
                    
                    # Check if next point exists and is not the last
                    if i + 1 < len(points) - 1:
                        cp2 = self._transform_point(points[i + 1])
                        # Calculate implied on-curve point between control points
                        implied_end = ((cp1[0] + cp2[0]) / 2, (cp1[1] + cp2[1]) / 2)
                        
                        # Draw curve to implied point
                        dist1 = ((cp1[0] - current_start[0])**2 + (cp1[1] - current_start[1])**2)**0.5
                        dist2 = ((implied_end[0] - cp1[0])**2 + (implied_end[1] - cp1[1])**2)**0.5
                        approx_length = dist1 + dist2
                        
                        min_steps = 4
                        max_steps = 20
                        steps = max(min_steps, min(max_steps, int(approx_length * self.curve_quality)))
                        
                        for j in range(1, steps + 1):
                            t = j / steps
                            mt = 1 - t
                            mt2 = mt * mt
                            t2 = t * t
                            
                            x = mt2 * current_start[0] + 2 * mt * t * cp1[0] + t2 * implied_end[0]
                            y = mt2 * current_start[1] + 2 * mt * t * cp1[1] + t2 * implied_end[1]
                            self.current_path.append((x, y))
                        
                        current_start = implied_end
    
    def closePath(self):
        """Close the current path."""
        if self.current_path and len(self.current_path) > 1:
            # Close the path by connecting to the first point
            if self.current_path[0] != self.current_path[-1]:
                self.current_path.append(self.current_path[0])
    
    def endPath(self):
        """End the current path and add it to the paths list."""
        if self.current_path:
            self.paths.append(self.current_path)
            self.current_path = []
    
    def draw_to_dxf(self):
        """Draw all paths to the DXF model space."""
        # Make sure to add the last path
        if self.current_path:
            self.paths.append(self.current_path)
        
        for path in self.paths:
            if len(path) > 1:
                # Create a polyline for each path
                polyline = self.msp.add_lwpolyline(path, close=False)
                polyline.dxf.layer = "TEXT_OUTLINES"


def find_font_by_name(font_name):
    """Find a font file by name (case-insensitive partial matching)."""
    fonts = find_all_fonts()
    font_name_lower = font_name.lower()
    
    # First, try exact match (case-insensitive)
    for name, path in fonts.items():
        if name.lower() == font_name_lower:
            return path
    
    # Then try partial match
    matches = []
    for name, path in fonts.items():
        if font_name_lower in name.lower():
            matches.append((name, path))
    
    if len(matches) == 1:
        return matches[0][1]
    elif len(matches) > 1:
        print(f"Multiple fonts found matching '{font_name}':")
        for name, path in matches:
            print(f"  {name}")
        print("\nPlease be more specific or use the full font name.")
        return None
    else:
        print(f"No font found matching '{font_name}'.")
        print("Use --list-fonts to see available fonts.")
        return None


def _load_font_and_get_scale(font_path, font_size, font_index, verbose=False):
    if verbose:
        print(f"Loading font: {font_path}")
    try:
        font = TTFont(font_path, fontNumber=font_index)
        if verbose:
            print("Font loaded successfully")
    except Exception as e:
        raise ValueError(f"Could not load font '{font_path}': {e}")

    if verbose:
        print("Getting font metrics...")
    try:
        head_table = font['head']
        units_per_em = head_table.unitsPerEm
        if verbose:
            print(f"Font units per em: {units_per_em}")
        scale = font_size / units_per_em
        if verbose:
            print(f"Scale factor: {scale}")
    except Exception as e:
        raise RuntimeError(f"Could not get font metrics: {e}")

    return font, scale


def _setup_dxf_document(verbose=False):
    if verbose:
        print("Creating DXF document...")
    try:
        doc = ezdxf.new('R2010')
        msp = doc.modelspace()
        doc.layers.add("TEXT_OUTLINES", color=1)  # Red color
        if verbose:
            print("DXF document created successfully")
    except Exception as e:
        raise RuntimeError(f"Could not create DXF document: {e}")
    return doc, msp


def _get_font_tables(font, verbose=False):
    if verbose:
        print("Getting glyph information...")
    try:
        glyph_set = font.getGlyphSet()
        if verbose:
            print("Glyph set obtained successfully")
    except Exception as e:
        raise RuntimeError(f"Could not get glyph set: {e}")

    try:
        cmap_subtable = None
        # Prioritize Windows Unicode BMP (3,1) or Symbol (3,0) tables
        for table in font.get('cmap').tables:
            if table.platformID == 3 and table.platEncID in [1, 0]:
                cmap_subtable = table
                if verbose:
                    print(f"Found a suitable cmap table: PlatformID={table.platformID}, PlatEncID={table.platEncID}")
                break
        
        cmap = None
        if cmap_subtable:
            cmap = cmap_subtable.cmap
        else:
            # If no suitable Windows cmap, try to get the best available
            if verbose:
                print("No specific Windows cmap found, trying getBestCmap()")
            cmap = font.getBestCmap()

        if not cmap:
            # If still no cmap, maybe there is another one we can use
            if font.get('cmap').tables:
                if verbose:
                    print("getBestCmap() failed, trying the first available cmap table.")
                cmap = font.get('cmap').tables[0].cmap

        if not cmap:
            raise RuntimeError("No character map found in font")

        if verbose:
            print(f"Character map obtained, {len(cmap)} characters available")
    except Exception as e:
        raise RuntimeError(f"Could not get character map: {e}")

    return glyph_set, cmap


def _get_char_advance(font, glyph_name, glyph_set, scale, spacing, font_size, char, verbose=False):
    x_advance = None
    # Method 1: Try hmtx table
    try:
        if 'hmtx' in font:
            hmtx_table = font['hmtx']
            if verbose:
                print(f"  hmtx table metrics keys: {list(hmtx_table.metrics.keys())[:10]}") # Print first 10 keys
            if glyph_name in hmtx_table.metrics:
                advance_width, _ = hmtx_table.metrics[glyph_name]
                x_advance = (advance_width * scale) * spacing
                if verbose:
                    print(f"  Advanced by {x_advance:.2f} (from hmtx table, width={advance_width})")
    except Exception as e:
        if verbose:
            print(f"  Could not get metrics from hmtx table: {e}")

    # Method 2: Try glyph set width
    if x_advance is None:
        try:
            glyph_obj = glyph_set[glyph_name]
            if hasattr(glyph_obj, 'width') and glyph_obj.width is not None:
                advance_width = glyph_obj.width
                x_advance = (advance_width * scale) * spacing
                if verbose:
                    print(f"  Advanced by {x_advance:.2f} (from glyph set, width={advance_width})")
        except Exception as e:
            if verbose:
                print(f"  Could not get width from glyph set: {e}")

    # Method 3: Fallback to a default advance if other methods fail
    if x_advance is None:
        # Default to a generic advance based on font_size if no other metric is available
        x_advance = (font_size * 0.5) * spacing  # A more generic fallback
        if verbose:
            print(f"  Advanced by {x_advance:.2f} (generic fallback)")

    return x_advance


def _get_kerning_adjustment(font, left_glyph, right_glyph, scale, verbose=False):
    """Get kerning adjustment for a pair of glyphs from the GPOS table."""
    if 'GPOS' not in font:
        return 0

    gpos_table = font['GPOS'].table
    if not hasattr(gpos_table, 'LookupList') or not gpos_table.LookupList:
        return 0

    for lookup in gpos_table.LookupList.Lookup:
        if not lookup or not hasattr(lookup, 'SubTable'):
            continue
        # LookupType 2 is for Pair Adjustment
        if lookup.LookupType == 2:
            for subtable in lookup.SubTable:
                if not subtable or not hasattr(subtable, 'Format'):
                    continue
                # Format 1 is for simple pair kerning
                if subtable.Format == 1:
                    if not hasattr(subtable, 'Coverage') or not hasattr(subtable.Coverage, 'glyphs'):
                        continue
                    
                    try:
                        idx = subtable.Coverage.glyphs.index(left_glyph)
                    except ValueError:
                        continue  # left_glyph not in coverage for this subtable

                    if not hasattr(subtable, 'PairSet') or idx >= len(subtable.PairSet):
                        continue

                    pair_set = subtable.PairSet[idx]
                    if not pair_set or not hasattr(pair_set, 'PairValueRecord'):
                        continue

                    for record in pair_set.PairValueRecord:
                        if record.SecondGlyph == right_glyph:
                            if hasattr(record, 'Value1') and hasattr(record.Value1, 'XAdvance'):
                                kerning_value = record.Value1.XAdvance
                                if verbose:
                                    print(f"  Kerning adjustment for ({left_glyph}, {right_glyph}): {kerning_value * scale:.2f}")
                                return kerning_value * scale
                # Format 2 is for class-based kerning
                elif subtable.Format == 2:
                    # This is more complex and less common for specific pairs.
                    # We will ignore it for now to keep the change simple.
                    pass
    return 0


def generate_surrounding_shape(min_x, min_y, max_x, max_y, surround, padding, gap, corner_radius, verbose=False):
    """
    Generate paths for the surrounding shape.
    """
    paths = []
    
    if surround == 'none':
        return paths

    # Apply padding
    min_x -= padding
    min_y -= padding
    max_x += padding
    max_y += padding

    if verbose:
        print(f"Generating surrounding shape: {surround}")
        print(f"Padding: {padding}, Gap: {gap}, Corner Radius: {corner_radius}")

    def create_rounded_rect(min_x, min_y, max_x, max_y, radius):
        """Create a single rounded rectangle path."""
        if radius == 0:
            # Simple rectangle
            return [[(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y), (min_x, min_y)]]

        # Ensure radius is not larger than half the shortest side
        radius = min(radius, (max_x - min_x) / 2, (max_y - min_y) / 2)
        if radius < 0: radius = 0 # Ensure non-negative radius

        path = []
        
        # Start at the bottom-left straight line segment start
        path.append((min_x + radius, min_y))

        # Bottom line segment
        path.append((max_x - radius, min_y))

        # Bottom-right arc
        path.extend(arc_points((max_x - radius, min_y + radius), radius, 270, 360))

        # Right line segment
        path.append((max_x, min_y + radius))
        path.append((max_x, max_y - radius))

        # Top-right arc
        path.extend(arc_points((max_x - radius, max_y - radius), radius, 0, 90))

        # Top line segment
        path.append((max_x - radius, max_y))
        path.append((min_x + radius, max_y))

        # Top-left arc
        path.extend(arc_points((min_x + radius, max_y - radius), radius, 90, 180))

        # Left line segment
        path.append((min_x, max_y - radius))
        path.append((min_x, min_y + radius))

        # Bottom-left arc
        path.extend(arc_points((min_x + radius, min_y + radius), radius, 180, 270))

        # Close the path by appending the first point
        path.append(path[0])
        return [path]

    def arc_points(center, radius, start_angle, end_angle, segments=16, reverse=False):
        """Generate points for an arc."""
        points = []
        if reverse:
            start_angle, end_angle = end_angle, start_angle
        
        for i in range(segments + 1):
            angle = math.radians(start_angle + (end_angle - start_angle) * i / segments)
            x = center[0] + radius * math.cos(angle)
            y = center[1] + radius * math.sin(angle)
            points.append((x, y))
        return points

    if surround == 'rectangle' or surround == 'double_rectangle':
        paths.extend(create_rounded_rect(min_x, min_y, max_x, max_y, corner_radius))

    if surround == 'double_rectangle':
        # Second rectangle with gap
        min_x_inner = min_x + gap
        min_y_inner = min_y + gap
        max_x_inner = max_x - gap
        max_y_inner = max_y - gap
        
        # Adjust corner radius for inner rectangle
        inner_radius = max(0, corner_radius - gap)
        
        paths.extend(create_rounded_rect(min_x_inner, min_y_inner, max_x_inner, max_y_inner, inner_radius))

    return paths


def text_to_dxf(font_path, text, output_path, font_size=20, spacing=1.0, curve_quality=0.5, verbose=False, kerning=True, surround='none', padding=5.0, gap=3.0, corner_radius=0.0, font_index=0):
    """
    Convert text to DXF outlines using the specified font.
    """
    font, scale = _load_font_and_get_scale(font_path, font_size, font_index, verbose)
    doc, msp = _setup_dxf_document(verbose)
    glyph_set, cmap = _get_font_tables(font, verbose)

    # Check if this is a symbol font by looking at the cmap keys
    is_symbol_font = False
    if cmap and cmap.keys():
        min_code = min(cmap.keys())
        if 0xF000 <= min_code <= 0xF8FF: # PUA range
            is_symbol_font = True
            if verbose:
                print("Detected a Symbol font based on character codes in the PUA range.")

    x_offset, y_offset = 0, 0
    successful_chars = 0
    previous_glyph_name = None  # For kerning
    all_paths = []
    surrounding_paths = []

    space_advance = 0
    try:
        # Get advance width for space character from hmtx table
        space_glyph_name = cmap.get(ord(' '))
        if space_glyph_name and 'hmtx' in font:
            space_advance, _ = font['hmtx'][space_glyph_name]
            space_advance *= scale
        else:
            # Fallback for space if not in hmtx
            space_advance = font_size * 0.4  # A more reasonable default
    except Exception:
        space_advance = font_size * 0.4 # Fallback

    if verbose:
        print(f"Space advance width: {space_advance}")

    for char in tqdm(text, desc="Processing characters", disable=verbose):
        if char == ' ':
            x_offset += space_advance  # Use calculated space advance
            if verbose:
                print(f"  Space character, advancing by {space_advance}")
            previous_glyph_name = None  # Reset for kerning
            continue

        char_code = ord(char)
        if is_symbol_font:
            # For symbol fonts, map ASCII to the PUA range
            if char_code <= 255: # Assuming ASCII input
                char_code += 0xF000
            if verbose:
                print(f"  Mapping character '{char}' to PUA code {char_code}")

        if char_code not in cmap:
            if verbose:
                print(f"  Warning: Character '{char}' (code: {char_code}) not found in font, skipping")
            previous_glyph_name = None  # Reset for kerning
            continue

        glyph_name = cmap[char_code]
        if verbose:
            print(f"  Glyph name: {glyph_name}")

        # Apply kerning adjustment
        if kerning and previous_glyph_name:
            adjustment = _get_kerning_adjustment(font, previous_glyph_name, glyph_name, scale, verbose)
            x_offset += adjustment

        try:
            glyph = glyph_set[glyph_name]
        except KeyError:
            if verbose:
                print(f"  Warning: Glyph '{glyph_name}' not found in font, skipping")
            previous_glyph_name = None  # Reset for kerning
            continue

        pen = DXFPen(msp, x_offset, y_offset, scale, curve_quality)
        try:
            glyph.draw(pen)
        except Exception as e:
            if verbose:
                print(f"  Warning: Could not draw glyph '{glyph_name}': {e}")
            continue

        pen.endPath()
        pen.draw_to_dxf()
        all_paths.extend(pen.paths)
        successful_chars += 1

        x_advance = _get_char_advance(font, glyph_name, glyph_set, scale, spacing, font_size, char, verbose)
        x_offset += x_advance
        
        previous_glyph_name = glyph_name  # Update for next iteration

    if verbose:
        print(f"Processed {successful_chars} characters successfully")

    # After generating all text paths, calculate the bounding box
    if all_paths and surround != 'none':
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')
        for path in all_paths:
            for x, y in path:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

        if verbose:
            print(f"Text bounding box: ({min_x:.2f}, {min_y:.2f}) to ({max_x:.2f}, {max_y:.2f})")

        # Generate surrounding shape
        surrounding_paths = generate_surrounding_shape(min_x, min_y, max_x, max_y, surround, padding, gap, corner_radius, verbose)
        for path in surrounding_paths:
            if len(path) > 1:
                polyline = msp.add_lwpolyline(path, close=True)
                polyline.dxf.layer = "SURROUND"

    try:
        if output_path:
            # Add a new layer for the surrounding shape
            if surround != 'none':
                doc.layers.add("SURROUND", color=2)  # Yellow color
            
            doc.saveas(output_path)
            print(f"DXF file saved successfully: {output_path}")
        if verbose:
            print("Summary:")
            print(f"  Text: '{text}'")
            print(f"  Font: {font_path}")
            print(f"  Font size: {font_size}mm")
            print(f"  Character spacing: {spacing}")
            print(f"  Kerning enabled: {kerning}")
            print(f"  Characters processed: {successful_chars}/{len([c for c in text if c != ' '])}")
    except Exception as e:
        raise RuntimeError(f"Could not save DXF file '{output_path}': {e}")
    finally:
        font.close()
        if verbose:
            print("Font closed successfully")
    return all_paths, surrounding_paths


def preview_paths(text_paths, surrounding_paths=None, preview=False, preview_file=None):
    """
    Display or save a preview of the paths using matplotlib.
    """
    if not preview and not preview_file:
        return

    plt.figure()
    for path in text_paths:
        if len(path) > 1:
            x, y = zip(*path)
            plt.plot(x, y, color='black', linewidth=1.5, label='Text Outlines')

    if surrounding_paths:
        for path in surrounding_paths:
            if len(path) > 1:
                x, y = zip(*path)
                plt.plot(x, y, color='blue', linestyle='--', linewidth=1.0, label='Surrounding Shape')
    
    plt.axis('equal')
    plt.title('text_to_dxf preview')
    plt.xlabel('X')
    plt.ylabel('Y')
    plt.grid(True)

    if preview_file:
        plt.savefig(preview_file)
        print(f"Preview saved to {preview_file}")

    if preview:
        plt.show()


def main():
    """Main function to handle command line arguments."""
    parser = argparse.ArgumentParser(description='Convert text to DXF font outlines')
    
    parser.add_argument('--list-fonts', action='store_true',
                       help='List all available system fonts and exit')
    parser.add_argument('text', nargs='?', help='Text string to convert')
    parser.add_argument('output', nargs='?', help='Output DXF file path')
    parser.add_argument('--font', type=str, default='Arial',
                       help='Font name to use (default: Arial) or path to font file')
    parser.add_argument('--font-index', type=int, default=0,
                       help='For .ttc font collections, specify the font index to use (default: 0)')
    parser.add_argument('--size', type=float, default=20, 
                       help='Font size in mm (default: 20)')
    parser.add_argument('--spacing', type=float, default=1.0,
                       help='Character spacing multiplier (default: 1.0)')
    parser.add_argument('--quality', choices=['low', 'medium', 'high'], default='high',
                       help='Curve quality: low, medium, or high (default: high)')
    parser.add_argument('--kerning', action=argparse.BooleanOptionalAction, default=True,
                        help='Enable/disable font kerning (default: --kerning)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose debug output')
    parser.add_argument('--preview', action='store_true',
                          help='Preview the generated paths using matplotlib')
    parser.add_argument('--preview-file', type=str,
                          help='Save the matplotlib preview to a file')

    # Arguments for surrounding shape
    parser.add_argument('--surround', type=str, choices=['none', 'rectangle', 'double_rectangle'], default='none',
                       help='Surround the text with a shape (default: none)')
    parser.add_argument('--padding', type=float, default=5.0,
                       help='Padding between text and surrounding shape in mm (default: 5.0)')
    parser.add_argument('--gap', type=float, default=3.0,
                       help='Gap between double rectangles in mm (default: 3.0)')
    parser.add_argument('--corner-radius', type=float, default=0.0,
                       help='Corner radius for surrounding rectangles in mm (default: 0.0)')
    
    args = parser.parse_args()
    
    # Handle font listing
    if args.list_fonts:
        list_fonts()
        return
    
    # Validate required arguments for text conversion
    if not args.text:
        parser.error('text argument is required (unless using --list-fonts)')
    
    # If preview is requested, output can be optional
    if not args.output and not args.preview and not args.preview_file:
        parser.error('output argument is required (unless using --preview or --preview-file)')
    
    # Determine font path
    font_path = None
    
    # Check if the font argument is a file path
    if os.path.isfile(args.font) and args.font.lower().endswith(('.ttf', '.otf', '.ttc')):
        # It's a font file path
        font_path = args.font
        if args.verbose:
            print(f"Using font file: {font_path}")
    else:
        # Treat it as a font name and search system fonts
        font_path = find_font_by_name(args.font)
        if not font_path:
            print(f"Could not find font '{args.font}'. Use --list-fonts to see available fonts.")
            sys.exit(1)
        if args.verbose:
            print(f"Using system font: {args.font}")
            print(f"Font path: {font_path}")
    
    quality_map = {
        'low': 0.1,
        'medium': 0.5,
        'high': 1.0
    }
    curve_quality = quality_map[args.quality]
    
    try:
        all_paths, surrounding_paths = text_to_dxf(font_path, args.text, args.output, args.size, args.spacing, curve_quality, args.verbose, args.kerning, args.surround, args.padding, args.gap, args.corner_radius, args.font_index)
        if args.preview or args.preview_file:
            preview_paths(all_paths, surrounding_paths, args.preview, args.preview_file)
    except Exception as e:
        import traceback
        print(f"Error: {e}")
        print(f"Full traceback:")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Example usage if run directly
    if len(sys.argv) == 1:
        print("Text to DXF Font Outline Generator")
        print("\nExample usage:")
        print("  # List all available fonts")
        print("  python text_to_dxf.py --list-fonts")
        print("\n  # Basic usage (uses Arial by default)")
        print("  python text_to_dxf.py \"Hello World\" output.dxf")
        print("\n  # Disable kerning")
        print("  python text_to_dxf.py \"Hello World\" output.dxf --no-kerning")
        print("\n  # Use different system fonts")
        print("  python text_to_dxf.py \"Hello World\" output.dxf --font \"Times New Roman\"")
        print("  python text_to_dxf.py \"Hello World\" output.dxf --font \"Helvetica\" --size 15")
        print("\n  # Use a specific font file")
        print("  python text_to_dxf.py \"Hello World\" output.dxf --font arial.ttf")
        print("  python text_to_dxf.py \"Hello World\" output.dxf --font LoveDays.ttf --size 25 --verbose")
        print("\n  # Preview the output without saving a DXF file")
        print("  python text_to_dxf.py \"Hello World\" --preview")
        print("\n  # Save the preview to a file")
        print("  python text_to_dxf.py \"Hello World\" --preview-file preview.png")
        print("\nRun with --help for more options")
    else:
        main()
