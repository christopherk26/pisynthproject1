#!/bin/bash

# Output file - save to user's Downloads folder
DOWNLOADS_DIR="$HOME/Downloads"
OUTPUT_FILE="$DOWNLOADS_DIR/AIpromptFORcodeAssist.md"

# Create Downloads directory if it doesn't exist
mkdir -p "$DOWNLOADS_DIR"

# Create new file with header
cat > "$OUTPUT_FILE" << 'EOF'

## Project Structure
\`\`\`
EOF

# Get the directory tree and append to file
tree -I "node_modules|.*|icons|dist|build" . >> "$OUTPUT_FILE"

# Add closing code block and section header
cat >> "$OUTPUT_FILE" << 'EOF'
\`\`\`

## File Contents
Below are the contents of each code file in the project:

EOF

# Function to process files
process_files() {
  # Find only code files with common code extensions, excluding config and lock files
  find . -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \
    -o -name "*.html" -o -name "*.css" -o -name "*.scss" -o -name "*.sass" \
    -o -name "*.xml" -o -name "*.md" -o -name "*.py" -o -name "*.java" -o -name "*.go" \
    -o -name "*.rb" -o -name "*.php" -o -name "*.c" -o -name "*.cpp" -o -name "*.h" \) \
    -not -path "*/node_modules/*" -not -path "*/\.*" -not -path "*/icons/*" \
    -not -path "*/dist/*" -not -path "*/build/*" \
    -not -name "package-lock.json" -not -name "yarn.lock" \
    -not -name "tsconfig*.json" -not -name "*.config.js" -not -name "*.config.ts" \
    -not -name "*.conf.js" -not -name "*.conf.ts" | sort | while read -r file; do
    
    # Add file header with path
    echo -e "\n### File: $file\n" >> "$OUTPUT_FILE"
    echo "\`\`\`" >> "$OUTPUT_FILE"
    
    # Add file contents
    cat "$file" >> "$OUTPUT_FILE"
    
    # Close code block
    echo -e "\`\`\`\n" >> "$OUTPUT_FILE"
    
    echo "Added $file"
  done
}

# Process all files
process_files

# Add instructions for AI
cat >> "$OUTPUT_FILE" << 'EOF'

## Instructions for AI


EOF

echo "Project analysis complete. Output saved to $OUTPUT_FILE"
echo "The file has been saved to your Downloads folder."