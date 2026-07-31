#!/usr/bin/env python3
"""Script to fix aspect description buttons in rooms.html - Version 3"""

file_path = "/Users/ainunfajar/SUDIN_ASKA/ai-agent-sekolah/dashboard/portal/templates/portal/sekolah/rooms.html"

# Read file
with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Process line by line
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]

    # Check if this is description display line without fallback
    if "{{ asp.description }}" in line and i + 2 < len(lines):
        # Check if next lines are just closing divs and endif
        if (
            "</div>" in lines[i + 1]
            and "</div>" in lines[i + 2]
            and i + 3 < len(lines)
            and "{% endif %}" in lines[i + 3]
        ):
            # Add the line with description, but wrap it
            indent = " " * 64  # matching indentation

            new_lines.append(indent + "{% if asp.description %}\n")
            new_lines.append(line)
            new_lines.append(indent + "{% else %}\n")
            new_lines.append(
                indent
                + '<small class="text-muted fst-italic">Tidak ada deskripsi untuk aspek ini.</small>\n'
            )
            new_lines.append(indent + "{% endif %}\n")

            # Add closing divs
            new_lines.append(lines[i + 1])
            new_lines.append(lines[i + 2])

            # Skip the endif line (i+3)
            i += 4
            continue

    new_lines.append(line)
    i += 1

# Write back
with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Fixed aspect description fallback messages!")
