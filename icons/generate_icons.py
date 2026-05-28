"""Generate PNG app icons for Penny Buddy using only standard library."""
import struct
import zlib
import os

def create_png(width, height, pixels):
    """Create a minimal PNG file from RGBA pixel data."""
    def chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack('>I', len(data)) + c + crc

    header = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))

    raw = b''
    for y in range(height):
        raw += b'\x00'  # filter byte
        for x in range(width):
            idx = (y * width + x) * 4
            raw += bytes(pixels[idx:idx+4])

    idat = chunk(b'IDAT', zlib.compress(raw, 9))
    iend = chunk(b'IEND', b'')
    return header + ihdr + idat + iend


def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(len(c1)))


def draw_icon(size):
    pixels = [0] * (size * size * 4)
    cx, cy = size / 2, size / 2
    r = size * 0.45  # main circle radius

    # Colors
    primary = (79, 70, 229)      # #4F46E5
    primary_dark = (55, 48, 163)  # #3730A3
    gold = (245, 158, 11)        # #F59E0B
    white = (255, 255, 255)

    for y in range(size):
        for x in range(size):
            idx = (y * size + x) * 4
            # Distance from center
            dx = x - cx
            dy = y - cy
            dist = (dx*dx + dy*dy) ** 0.5

            if dist <= r:
                # Gradient from primary to primary_dark (diagonal)
                t = min(1.0, max(0.0, (x + y) / (size * 2)))
                bg = lerp_color(primary, primary_dark, t)

                # Inner circle for "coin" effect
                inner_r = size * 0.28
                inner_dist = ((x - cx)**2 + (y - cy * 0.9)**2) ** 0.5
                if inner_dist <= inner_r:
                    # Lighter circle
                    alpha = max(0, 1 - inner_dist / inner_r)
                    col = lerp_color(bg, (255, 255, 255), 0.12 + alpha * 0.05)
                else:
                    col = bg

                # Gold accent circle (top-right)
                accent_cx = cx + r * 0.5
                accent_cy = cy - r * 0.45
                accent_r = size * 0.09
                accent_dist = ((x - accent_cx)**2 + (y - accent_cy)**2) ** 0.5
                if accent_dist <= accent_r:
                    col = gold

                # Anti-alias the outer edge
                edge = r - dist
                if edge < 1.5:
                    a = int(min(255, edge / 1.5 * 255))
                else:
                    a = 255

                pixels[idx] = col[0]
                pixels[idx+1] = col[1]
                pixels[idx+2] = col[2]
                pixels[idx+3] = a
            else:
                pixels[idx:idx+4] = [0, 0, 0, 0]

    # Draw "PB" text as simple pixel art in center
    draw_pb_text(pixels, size)

    return pixels


def draw_pb_text(pixels, size):
    """Draw 'PB' as blocky pixel text centered on the icon."""
    # Simple 5x7 pixel font for P and B
    P = [
        [1,1,1,0],
        [1,0,0,1],
        [1,0,0,1],
        [1,1,1,0],
        [1,0,0,0],
        [1,0,0,0],
        [1,0,0,0],
    ]
    B = [
        [1,1,1,0],
        [1,0,0,1],
        [1,0,0,1],
        [1,1,1,0],
        [1,0,0,1],
        [1,0,0,1],
        [1,1,1,0],
    ]

    block = max(1, size // 28)
    gap = max(1, block)

    p_w = len(P[0]) * block
    b_w = len(B[0]) * block
    total_w = p_w + gap + b_w
    total_h = 7 * block

    start_x = (size - total_w) // 2
    start_y = (size - total_h) // 2 - size // 20

    def draw_char(char_map, ox, oy):
        for row in range(7):
            for col in range(len(char_map[0])):
                if char_map[row][col]:
                    for by in range(block):
                        for bx in range(block):
                            px = ox + col * block + bx
                            py = oy + row * block + by
                            if 0 <= px < size and 0 <= py < size:
                                idx = (py * size + px) * 4
                                if pixels[idx+3] > 0:  # only draw on non-transparent
                                    pixels[idx] = 255
                                    pixels[idx+1] = 255
                                    pixels[idx+2] = 255
                                    pixels[idx+3] = 255

    draw_char(P, start_x, start_y)
    draw_char(B, start_x + p_w + gap, start_y)


if __name__ == '__main__':
    sizes = [72, 96, 128, 144, 152, 192, 384, 512]
    out_dir = os.path.dirname(os.path.abspath(__file__))

    for s in sizes:
        print(f'Generating {s}x{s} icon...')
        px = draw_icon(s)
        png_data = create_png(s, s, px)
        path = os.path.join(out_dir, f'icon-{s}x{s}.png')
        with open(path, 'wb') as f:
            f.write(png_data)
        print(f'  Saved: {path}')

    print('All icons generated!')
