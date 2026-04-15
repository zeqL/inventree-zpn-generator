from plugin import InvenTreePlugin
from plugin.mixins import EventMixin, SettingsMixin
from part.models import Part, PartParameter

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

import logging
import re

logger = logging.getLogger("inventree")

# SAPN format constants
SAPN_PREFIX = "SAPN"
SAPN_CCC_PARAM = "SA_CCC"
SAPN_SS_PARAM = "SA_SS"
SAPN_MAX_SEQUENCE = 99999
SAPN_RETRY_ATTEMPTS = 10

# Regex patterns for validation
CCC_PATTERN = re.compile(r"^[A-Z]{3}$")
SS_PATTERN = re.compile(r"^\d{2}$")


def validate_ccc(value: str) -> bool:
    """Validate CCC component (3 uppercase letters)."""
    return bool(CCC_PATTERN.match(value))


def validate_ss(value: str) -> bool:
    """Validate SS component (2 digits)."""
    return bool(SS_PATTERN.match(value))


def get_part_parameter_value(part, parameter_name: str) -> str | None:
    """Get the value of a part parameter by name."""
    try:
        param = PartParameter.objects.filter(
            part=part,
            template__name=parameter_name
        ).first()
        if param:
            return param.data
    except Exception as e:
        logger.warning(f"SAPN Generator: Error reading parameter {parameter_name}: {e}")
    return None


def compute_next_sapn(ccc: str, ss: str) -> str | None:
    """
    Compute the next SAPN for the given CCC and SS values.
    
    Args:
        ccc: 3-letter category code (e.g., 'ELC')
        ss: 2-digit subcategory code (e.g., '11')
    
    Returns:
        The next SAPN string (e.g., 'SAPN-ELC-11-00042') or None if max reached.
    
    Raises:
        ValueError: If the next sequence number would exceed 99999.
    """
    prefix = f"{SAPN_PREFIX}-{ccc}-{ss}-"
    
    # Find the maximum existing IPN with this prefix
    # Since the suffix is fixed-width 5 digits, lexicographic ordering works
    latest = Part.objects.filter(
        IPN__startswith=prefix
    ).order_by("-IPN").first()
    
    if latest:
        # Extract the numeric suffix
        try:
            suffix = latest.IPN[len(prefix):]
            current_num = int(suffix)
            next_num = current_num + 1
        except (ValueError, IndexError) as e:
            logger.warning(f"SAPN Generator: Could not parse existing IPN '{latest.IPN}': {e}")
            next_num = 1
    else:
        next_num = 1
    
    # Check for overflow
    if next_num > SAPN_MAX_SEQUENCE:
        raise ValueError(
            f"SAPN sequence overflow for bucket ({ccc}, {ss}): "
            f"next number {next_num} exceeds maximum {SAPN_MAX_SEQUENCE}. "
            "Cannot generate more IPNs for this category/subcategory combination."
        )
    
    return f"{prefix}{next_num:05d}"


def generate_sapn_for_part(part) -> str | None:
    """
    Generate a SAPN for the given part based on its SA_CCC and SA_SS parameters.
    
    Args:
        part: InvenTree Part object
    
    Returns:
        Generated SAPN string or None if generation is not possible.
    """
    # Read CCC from part parameter SA_CCC
    ccc = get_part_parameter_value(part, SAPN_CCC_PARAM)
    if not ccc:
        logger.warning(
            f"SAPN Generator: Part {part.pk} missing required parameter '{SAPN_CCC_PARAM}'. "
            "Cannot generate SAPN."
        )
        return None
    
    ccc = ccc.strip().upper()
    if not validate_ccc(ccc):
        logger.warning(
            f"SAPN Generator: Part {part.pk} has invalid {SAPN_CCC_PARAM}='{ccc}'. "
            f"Must match pattern ^[A-Z]{{3}}$. Cannot generate SAPN."
        )
        return None
    
    # Read SS from part parameter SA_SS
    ss = get_part_parameter_value(part, SAPN_SS_PARAM)
    if not ss:
        logger.warning(
            f"SAPN Generator: Part {part.pk} missing required parameter '{SAPN_SS_PARAM}'. "
            "Cannot generate SAPN."
        )
        return None
    
    ss = ss.strip()
    if not validate_ss(ss):
        logger.warning(
            f"SAPN Generator: Part {part.pk} has invalid {SAPN_SS_PARAM}='{ss}'. "
            f"Must match pattern ^\\d{{2}}$. Cannot generate SAPN."
        )
        return None
    
    try:
        return compute_next_sapn(ccc, ss)
    except ValueError as e:
        logger.error(f"SAPN Generator: {e}")
        return None


class ZPNGeneratorPlugin(EventMixin, SettingsMixin, InvenTreePlugin):
    """Plugin to generate SAPN (Sequential Auto Part Number) automatically.
    
    SAPN Format: SAPN-{CCC}-{SS}-{NNNNN}
    - CCC: 3-letter code from part parameter SA_CCC
    - SS: 2-digit code from part parameter SA_SS  
    - NNNNN: 5-digit zero-padded sequence number per (CCC, SS) bucket
    
    Example: SAPN-ELC-11-00042
    """

    AUTHOR = "Nicolas Désilles, Modified from Nichlas W."
    DESCRIPTION = (
        "Plugin for automatically assigning SAPN (Still Asking Part Numbers) to parts. "
        "Uses SA_CCC and SA_SS part parameters to determine category codes. "
        "Format: SAPN-{CCC}-{SS}-{NNNNN}"
    )
    VERSION = "0.1.0"
    WEBSITE = "https://github.com/still-asking/inventree-sapn-generator"

    NAME = "ZPNGenerator"
    SLUG = "zpngen"
    TITLE = "ZPN Generator"

    SETTINGS = {
        "ACTIVE": {
            "name": "Active",
            "description": "ZPN generator is active",
            "validator": bool,
            "default": True,
        },
        "ON_CREATE": {
            "name": "On Create",
            "description": "Generate ZPN when creating new parts",
            "validator": bool,
            "default": True,
        },
        "ON_CHANGE": {
            "name": "On Change",
            "description": "Generate ZPN when editing parts (only if IPN is empty)",
            "validator": bool,
            "default": False,
        },
    }

    def wants_process_event(self, event):
        """Lets InvenTree know what events to listen for."""

        if not self.get_setting("ACTIVE"):
            return False

        if event == "part_part.saved":
            return self.get_setting("ON_CHANGE")

        if event == "part_part.created":
            return self.get_setting("ON_CREATE")

        return False

    def process_event(self, event, *args, **kwargs):
        """Main plugin handler function for SAPN generation."""

        if not self.get_setting("ACTIVE"):
            return False

        id = kwargs.pop("id", None)
        model = kwargs.pop("model", None)

        # Events can fire on unrelated models
        if model != "Part":
            logger.debug("SAPN Generator: Event model is not Part")
            return

        # Fetch the part
        try:
            part = Part.objects.get(id=id)
        except Part.DoesNotExist:
            logger.warning(f"SAPN Generator: Part with id {id} not found")
            return

        # Don't create IPNs for parts that already have one
        if part.IPN:
            logger.debug(f"SAPN Generator: Part {id} already has IPN '{part.IPN}', skipping")
            return

        # Attempt SAPN generation with retry for concurrency handling
        for attempt in range(1, SAPN_RETRY_ATTEMPTS + 1):
            try:
                new_ipn = generate_sapn_for_part(part)
                
                if not new_ipn:
                    # Generation failed due to missing/invalid parameters - already logged
                    return
                
                # Use atomic transaction for the save
                with transaction.atomic():
                    # Re-check current max to avoid race conditions
                    part.refresh_from_db()
                    
                    # Double-check IPN hasn't been set in the meantime
                    if part.IPN:
                        logger.debug(f"SAPN Generator: Part {id} IPN was set during processing, skipping")
                        return
                    
                    # Recompute SAPN to get the latest sequence number
                    ccc = get_part_parameter_value(part, SAPN_CCC_PARAM)
                    ss = get_part_parameter_value(part, SAPN_SS_PARAM)
                    
                    if ccc and ss:
                        ccc = ccc.strip().upper()
                        ss = ss.strip()
                        new_ipn = compute_next_sapn(ccc, ss)
                    
                    part.IPN = new_ipn
                    part.save()
                
                logger.info(f"SAPN Generator: Assigned IPN '{new_ipn}' to Part {id}")
                return
                
            except IntegrityError as e:
                # Likely a uniqueness conflict - retry with new sequence
                logger.warning(
                    f"SAPN Generator: Integrity error on attempt {attempt}/{SAPN_RETRY_ATTEMPTS} "
                    f"for Part {id}: {e}"
                )
                if attempt == SAPN_RETRY_ATTEMPTS:
                    logger.error(
                        f"SAPN Generator: Failed to assign IPN to Part {id} after "
                        f"{SAPN_RETRY_ATTEMPTS} attempts due to integrity errors"
                    )
            except ValueError as e:
                # Sequence overflow
                logger.error(f"SAPN Generator: {e}")
                return
            except Exception as e:
                logger.error(f"SAPN Generator: Unexpected error assigning IPN to Part {id}: {e}")
                return

        return
