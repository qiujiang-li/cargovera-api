import re
def parse_name(full_name: str) -> tuple[str, str]:
    """
    Parses a full name string into a first name and last name.
    
    Args:
        full_name (str): A string containing a full name.

    Returns:
        tuple[str, str]: A tuple containing (first_name, last_name).
                        If only one name is given, last_name will be an empty string.
    """
    # Strip whitespace and split on spaces
    parts = full_name.strip().split()

    if not parts:
        return "", ""

    if len(parts) == 1:
        return parts[0], parts[0]

    first_name = parts[0]
    last_name = " ".join(parts[1:])  # In case of middle names or compound surnames
    return first_name, last_name

def parse_zipcode(zipcode: str) -> tuple[str, str]:
    """
    Parses a US ZIP code string into ZIP5 and ZIP4 components.

    Args:
        zipcode (str): A ZIP code string (e.g., '12345', '12345-6789', '123456789').

    Returns:
        tuple[str, str]: (ZIP5, ZIP4) — ZIP4 will be an empty string if not present.
    """
    if not zipcode:
        return "", ""

    # Remove any non-digit characters (e.g., dash)
    digits = re.sub(r"[^\d]", "", zipcode)

    if len(digits) == 5:
        return digits, ""
    elif len(digits) == 9:
        return digits[:5], digits[5:]
    else:
        # Invalid format
        return "", ""

def is_valid_upc(upc: str) -> bool:
    """Validate a 12-digit UPC-A code."""
    if not upc.isdigit() or len(upc) != 12:
        return False

    digits = [int(d) for d in upc]
    odd_sum = sum(digits[i] for i in range(0, 11, 2))
    even_sum = sum(digits[i] for i in range(1, 11, 2))
    total = (odd_sum * 3) + even_sum
    check_digit = (10 - (total % 10)) % 10

    return check_digit == digits[-1]

def is_valid_zipcode(zipcode: str) -> bool:
    """
    Validates a US ZIP code.
    Accepts 5-digit ZIPs (e.g., '12345') or ZIP+4 format (e.g., '12345-6789').

    Args:
        zipcode (str): ZIP code to validate.

    Returns:
        bool: True if valid, False otherwise.
    """
    pattern = re.compile(r"^\d{5}(-\d{4})?$")
    return bool(pattern.match(zipcode))