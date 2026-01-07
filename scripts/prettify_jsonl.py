#!/usr/bin/env python3
"""
JSONL Prettifier - Pretty-print JSONL (JSON Lines) files.

Usage:
    python scripts/prettify_jsonl.py <input.jsonl> [output.json]
    python scripts/prettify_jsonl.py <input.jsonl> --stdout
    python scripts/prettify_jsonl.py <input.jsonl> --compact
    python scripts/prettify_jsonl.py <input.jsonl> --indent 4
    cat input.jsonl | python scripts/prettify_jsonl.py --stdin

Can also be used as a Python module:
    from scripts.prettify_jsonl import prettify_jsonl_file
    prettify_jsonl_file('input.jsonl', 'output.json', indent=2)
"""

import json
import sys
import argparse
import tempfile
import shutil
from pathlib import Path
from typing import TextIO, Optional, Iterator, Union, List


def prettify_jsonl(
    input_file: TextIO,
    output_file: Optional[TextIO] = None,
    indent: int = 2,
    compact: bool = False,
    show_line_numbers: bool = False,
    filter_stage: Optional[str] = None,
    max_lines: Optional[int] = None
) -> int:
    """
    Prettify a JSONL file.
    
    Args:
        input_file: Input file handle (or stdin).
        output_file: Output file handle (or stdout if None).
        indent: JSON indentation (0 for compact).
        compact: If True, output as compact JSON array.
        show_line_numbers: If True, prefix each entry with line number.
        filter_stage: If provided, only show entries with this stage.
        max_lines: Maximum number of lines to process.
    
    Returns:
        Number of entries processed.
    """
    if output_file is None:
        output_file = sys.stdout
    
    entries = []
    line_num = 0
    
    try:
        for line_num, line in enumerate(input_file, 1):
            if max_lines and line_num > max_lines:
                break
            
            line = line.strip()
            if not line:
                continue
            
            try:
                entry = json.loads(line)
                
                # Filter by stage if requested
                if filter_stage and entry.get('stage') != filter_stage:
                    continue
                
                entries.append(entry)
                
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON on line {line_num}: {e}", file=sys.stderr)
                continue
        
        if compact:
            # Output as single compact JSON array
            json.dump(entries, output_file, indent=indent, ensure_ascii=False)
            output_file.write('\n')
        else:
            # Output each entry as prettified JSON with separators
            for i, entry in enumerate(entries):
                if show_line_numbers:
                    output_file.write(f"# Entry {i + 1} (line {line_num - len(entries) + i + 1})\n")
                
                json.dump(entry, output_file, indent=indent, ensure_ascii=False)
                output_file.write('\n')
                
                if i < len(entries) - 1:
                    output_file.write('\n' + '=' * 80 + '\n\n')
        
        return len(entries)
    
    except KeyboardInterrupt:
        print(f"\nInterrupted at line {line_num}", file=sys.stderr)
        return len(entries)
    except Exception as e:
        print(f"Error processing line {line_num}: {e}", file=sys.stderr)
        raise


def find_all_jsonl_files(
    root_dir: Union[str, Path],
    recursive: bool = True
) -> List[Path]:
    """
    Find all .jsonl files in a directory.
    
    Args:
        root_dir: Root directory to search.
        recursive: If True, search recursively.
    
    Returns:
        List of .jsonl file paths.
    """
    root_path = Path(root_dir)
    if not root_path.exists():
        return []
    
    if recursive:
        return sorted(root_path.rglob("*.jsonl"))
    else:
        return sorted(root_path.glob("*.jsonl"))


def prettify_jsonl_file(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    indent: int = 2,
    compact: bool = False,
    show_line_numbers: bool = False,
    filter_stage: Optional[str] = None,
    max_lines: Optional[int] = None,
    in_place: bool = False
) -> int:
    """
    Prettify a JSONL file (convenience function).
    
    Args:
        input_path: Path to input JSONL file.
        output_path: Path to output file (None for stdout, ignored if in_place=True).
        indent: JSON indentation (0 for compact).
        compact: If True, output as compact JSON array.
        show_line_numbers: If True, prefix each entry with line number.
        filter_stage: If provided, only show entries with this stage.
        max_lines: Maximum number of lines to process.
        in_place: If True, overwrite the input file with prettified version.
    
    Returns:
        Number of entries processed.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    # If in-place, write to a temp file first, then replace
    if in_place:
        with open(input_path, 'r', encoding='utf-8') as input_file:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.jsonl') as tmp_file:
                tmp_path = Path(tmp_file.name)
                count = prettify_jsonl(
                    input_file=input_file,
                    output_file=tmp_file,
                    indent=indent,
                    compact=compact,
                    show_line_numbers=show_line_numbers,
                    filter_stage=filter_stage,
                    max_lines=max_lines
                )
        
        # Replace original with prettified version
        shutil.move(str(tmp_path), str(input_path))
        return count
    
    # Normal operation
    with open(input_path, 'r', encoding='utf-8') as input_file:
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as output_file:
                return prettify_jsonl(
                    input_file=input_file,
                    output_file=output_file,
                    indent=indent,
                    compact=compact,
                    show_line_numbers=show_line_numbers,
                    filter_stage=filter_stage,
                    max_lines=max_lines
                )
        else:
            return prettify_jsonl(
                input_file=input_file,
                output_file=None,
                indent=indent,
                compact=compact,
                show_line_numbers=show_line_numbers,
                filter_stage=filter_stage,
                max_lines=max_lines
            )


def main():
    parser = argparse.ArgumentParser(
        description="Prettify JSONL (JSON Lines) files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Prettify to stdout
  python scripts/prettify_jsonl.py data/sessions/session.jsonl
  
  # Save to file
  python scripts/prettify_jsonl.py data/sessions/session.jsonl output.json
  
  # Prettify all .jsonl files in project (creates .json versions)
  python scripts/prettify_jsonl.py --all
  
  # Prettify all .jsonl files in a directory
  python scripts/prettify_jsonl.py --directory data/sessions
  
  # Prettify all .jsonl files in-place (overwrites originals)
  python scripts/prettify_jsonl.py --all --in-place
  
  # Dry run to see what would be processed
  python scripts/prettify_jsonl.py --all --dry-run
  
  # Compact JSON array output
  python scripts/prettify_jsonl.py data/sessions/session.jsonl --compact
  
  # Filter by stage
  python scripts/prettify_jsonl.py data/sessions/session.jsonl --stage refinement
  
  # Read from stdin
  cat data/sessions/session.jsonl | python scripts/prettify_jsonl.py --stdin
  
  # First 10 entries only
  python scripts/prettify_jsonl.py data/sessions/session.jsonl --max-lines 10
        """
    )
    
    parser.add_argument(
        'input',
        nargs='?',
        type=Path,
        help='Input JSONL file (or use --stdin)'
    )
    
    parser.add_argument(
        'output',
        nargs='?',
        type=Path,
        help='Output file (default: stdout)'
    )
    
    parser.add_argument(
        '--stdin',
        action='store_true',
        help='Read from stdin instead of file'
    )
    
    parser.add_argument(
        '--stdout',
        action='store_true',
        help='Force output to stdout (even if output file specified)'
    )
    
    parser.add_argument(
        '--indent',
        type=int,
        default=2,
        help='JSON indentation (default: 2, use 0 for compact)'
    )
    
    parser.add_argument(
        '--compact',
        action='store_true',
        help='Output as single compact JSON array instead of separated entries'
    )
    
    parser.add_argument(
        '--line-numbers',
        action='store_true',
        dest='show_line_numbers',
        help='Show line numbers for each entry'
    )
    
    parser.add_argument(
        '--stage',
        dest='filter_stage',
        help='Only show entries with this stage (e.g., "refinement", "synthesis")'
    )
    
    parser.add_argument(
        '--max-lines',
        type=int,
        help='Maximum number of lines to process'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='Process all .jsonl files in the project (recursive search)'
    )
    
    parser.add_argument(
        '--directory',
        type=Path,
        help='Process all .jsonl files in the specified directory (recursive)'
    )
    
    parser.add_argument(
        '--recursive',
        action='store_true',
        default=True,
        help='When using --directory, search recursively (default: True)'
    )
    
    parser.add_argument(
        '--no-recursive',
        action='store_false',
        dest='recursive',
        help='When using --directory, search only in the specified directory (not recursive)'
    )
    
    parser.add_argument(
        '--in-place',
        action='store_true',
        help='Overwrite input file(s) with prettified version (use with caution!)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show which files would be processed without actually processing them'
    )
    
    args = parser.parse_args()
    
    # Handle batch processing (--all or --directory)
    if args.all or args.directory:
        if args.stdin:
            print("Error: Cannot use --stdin with --all or --directory", file=sys.stderr)
            sys.exit(1)
        
        # Determine search directory
        if args.all:
            # Search from project root (where script is located)
            search_dir = Path(__file__).parent.parent
        else:
            search_dir = args.directory
            if not search_dir.exists():
                print(f"Error: Directory not found: {search_dir}", file=sys.stderr)
                sys.exit(1)
        
        # Find all .jsonl files
        jsonl_files = find_all_jsonl_files(search_dir, recursive=args.recursive)
        
        if not jsonl_files:
            print(f"No .jsonl files found in {search_dir}", file=sys.stderr)
            sys.exit(0)
        
        if args.dry_run:
            print(f"Would process {len(jsonl_files)} .jsonl file(s):", file=sys.stderr)
            for f in jsonl_files:
                print(f"  {f}", file=sys.stderr)
            sys.exit(0)
        
        # Process each file
        total_files = 0
        total_entries = 0
        errors = []
        
        for jsonl_file in jsonl_files:
            try:
                if args.in_place:
                    count = prettify_jsonl_file(
                        input_path=jsonl_file,
                        indent=args.indent,
                        compact=args.compact,
                        show_line_numbers=args.show_line_numbers,
                        filter_stage=args.filter_stage,
                        max_lines=args.max_lines,
                        in_place=True
                    )
                    print(f"✓ {jsonl_file}: {count} entries (in-place)", file=sys.stderr)
                else:
                    # Generate output filename
                    if args.output:
                        # If single output specified, only process first file
                        if total_files > 0:
                            print(f"Warning: --output specified but multiple files found. Only processing first file.", file=sys.stderr)
                            break
                        output_path = args.output
                    else:
                        # Create prettified version with .json extension
                        output_path = jsonl_file.with_suffix('.json')
                    
                    count = prettify_jsonl_file(
                        input_path=jsonl_file,
                        output_path=output_path,
                        indent=args.indent,
                        compact=args.compact,
                        show_line_numbers=args.show_line_numbers,
                        filter_stage=args.filter_stage,
                        max_lines=args.max_lines
                    )
                    print(f"✓ {jsonl_file} → {output_path}: {count} entries", file=sys.stderr)
                
                total_files += 1
                total_entries += count
                
            except Exception as e:
                error_msg = f"✗ {jsonl_file}: {e}"
                print(error_msg, file=sys.stderr)
                errors.append(error_msg)
        
        print(f"\nProcessed {total_files} file(s), {total_entries} total entries.", file=sys.stderr)
        if errors:
            print(f"Errors: {len(errors)}", file=sys.stderr)
        sys.exit(0 if not errors else 1)
    
    # Single file processing
    if args.stdin:
        input_file = sys.stdin
    elif args.input:
        if not args.input.exists():
            print(f"Error: Input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        input_file = open(args.input, 'r', encoding='utf-8')
    else:
        print("Error: Must provide input file, use --stdin, or use --all/--directory", file=sys.stderr)
        parser.print_help()
        sys.exit(1)
    
    # Determine output
    if args.stdout or not args.output:
        output_file = None  # Will use stdout
    else:
        output_file = open(args.output, 'w', encoding='utf-8')
    
    try:
        count = prettify_jsonl(
            input_file=input_file,
            output_file=output_file,
            indent=args.indent,
            compact=args.compact,
            show_line_numbers=args.show_line_numbers,
            filter_stage=args.filter_stage,
            max_lines=args.max_lines
        )
        
        if output_file and output_file != sys.stdout:
            output_file.close()
            print(f"Processed {count} entries. Output written to {args.output}", file=sys.stderr)
        else:
            print(f"Processed {count} entries.", file=sys.stderr)
    
    finally:
        if input_file != sys.stdin:
            input_file.close()
        if output_file and output_file != sys.stdout:
            output_file.close()


if __name__ == '__main__':
    main()

