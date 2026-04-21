import logging
import re

from common.models import Parameter, ParameterTemplate
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from part.models import Part
from plugin import InvenTreePlugin
from plugin.mixins import EventMixin, SettingsMixin

logger = logging.getLogger("inventree")

# ZPN format constants
ZPN_CAT_PARAM = "ZPN_CAT"
ZPN_SUBCAT_PARAM = "ZPN_SUBCAT"
ZPN_MAX_SEQUENCE = 999999
ZPN_RETRY_ATTEMPTS = 10

# Regex patterns for validation
ZPN_CAT_PATTERN = re.compile(r"^[A-Z0-9]{3}$")
ZPN_SUBCAT_PATTERN = re.compile(r"^\d{2}$")


def validate_ccc(value: str) -> bool:
    """Validate CCC component (3 uppercase letters)."""
    return bool(ZPN_CAT_PATTERN.match(value))


def validate_ss(value: str) -> bool:
    """Validate SS component (2 digits)."""
    return bool(ZPN_SUBCAT_PATTERN.match(value))


def get_part_parameter_value(part, parameter_name: str) -> str | None:
    """Get the value of a part parameter by name."""
    try:
        "param = PartCategory.objects.filter(part=part, name=parameter_name).first()"
        param = Parameter.objects.filter(
            model_id=part.id, template__name=parameter_name
        ).first()
        if param:
            return param.data
    except Exception as e:
        logger.warning(f"ZPN Generator: Error reading parameter {parameter_name}: {e}")
    return None


def compute_next_zpn(ccc: str, ss: str) -> str | None:
    """
    Compute the next ZPN for the given ZPN_CAT_PARAM and ZPN_SUBCAT_PARAM values.

    Args:
        ZPN_CAT_PARAM: 3-alphanumeric category code (e.g., '1AA' or 'AAA')
        ZPN_SUBCAT_PARAM: 2-digit subcategory code (e.g., '11')

    Returns:
        The next ZPN string (e.g., '1AA01000123') or None if max reached.

    Raises:
        ValueError: If the next sequence number would exceed 999999.
    """
    prefix = f"{ccc}{ss}"

    # Find the maximum existing IPN with this prefix
    # Since the suffix is fixed-width 5 digits, lexicographic ordering works
    latest = Part.objects.filter(IPN__startswith=prefix).order_by("-IPN").first()

    if latest:
        # Extract the numeric suffix
        try:
            suffix = latest.IPN[len(prefix) :]
            current_num = int(suffix)
            next_num = current_num + 1
        except (ValueError, IndexError) as e:
            logger.warning(
                f"ZPN Generator: Could not parse existing IPN '{latest.IPN}': {e}"
            )
            next_num = 1
    else:
        next_num = 1

    # Check for overflow
    if next_num > ZPN_MAX_SEQUENCE:
        raise ValueError(
            f"ZPN sequence overflow for bucket ({ccc}, {ss}): "
            f"next number {next_num} exceeds maximum {ZPN_MAX_SEQUENCE}. "
            "Cannot generate more IPNs for this category/subcategory combination."
        )

    return f"{prefix}{next_num:06d}"


def generate_zpn_for_part(part) -> str | None:
    """
    Generate a ZPN for the given part based on its ZPN_CAT_PARAM and ZPN_SUBCAT_PARAM parameters.

    Args:
        part: InvenTree Part object

    Returns:
        Generated ZPN string or None if generation is not possible.
    """
    # Read CCC from part parameter ZPN_CAT_PARAM
    ccc = get_part_parameter_value(part, ZPN_CAT_PARAM)
    if not ccc:
        logger.warning(
            f"ZPN Generator: Part {part.pk} missing required parameter '{ZPN_CAT_PARAM}'. "
            "Cannot generate ZPN."
        )
        return None

    ccc = ccc.strip().upper()
    if not validate_ccc(ccc):
        logger.warning(
            f"ZPN Generator: Part {part.pk} has invalid {ZPN_CAT_PARAM}='{ccc}'. "
            f"Must match pattern ^[A-Z0-9]{{3}}$. Cannot generate ZPN."
        )
        return None

    # Read SS from part parameter ZPN_SUBCAT_PARAM
    ss = get_part_parameter_value(part, ZPN_SUBCAT_PARAM)

    # If default subcat value is ON set ss to ZPN_SUBCAT default value
    if not ss:
        if 'ZPN_SUBCAT_DEFVAL_ON' is True:
        ss = 'ZPN_SUBCAT_DEFVAL'
        else:
            logger.warning(
                f"ZPN Generator: Part {part.pk} missing required parameter '{ZPN_SUBCAT_PARAM}'. "
                "Cannot generate ZPN."
            )
            return None

    ss = ss.strip()
    if not validate_ss(ss):
        logger.warning(
            f"ZPN Generator: Part {part.pk} has invalid {ZPN_SUBCAT_PARAM}='{ss}'. "
            f"Must match pattern ^\\d{{2}}$. Cannot generate ZPN."
        )
        return None

    try:
        return compute_next_zpn(ccc, ss)
    except ValueError as e:
        logger.error(f"ZPN Generator: {e}")
        return None


class ZPNGeneratorPlugin(EventMixin, SettingsMixin, InvenTreePlugin):
    """Plugin to generate ZPN (Z Part Number) automatically.

    ZPN Format: {CCC}{SS}{NNNNNN}
    - CCC: 3-Alphanumeric code from part parameter ZPN_CAT_PARAM
    - SS: 2-digit code from part parameter ZPN_SUBCAT_PARAM
    - NNNNNN: 6-digit zero-padded sequence number per (CCC, SS) bucket

    Example: 1AA01123456
    """

    AUTHOR = "Simon F. Modified from Nichlas W. and Nicolas Désilles"
    DESCRIPTION = (
        "Plugin for automatically assigning IPN to parts. Prefix customisation for categories and subcategories (template configuration) "
        "Uses ZPN_CAT_PARAM and ZPN_SUBCAT_PARAM part parameters to determine category codes. "
        "Format: {CCC}{SS}{NNNNNN}"
    )
    VERSION = "0.2.0"
    WEBSITE = "https://github.com/zeqL/inventree-zpn-generator/"

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
        "ZPN_SUBCAT_DEFVAL_ON": {
            "name": "ZPN SUBCAT Default Value ON/OFF",
            "description": "Apply a default ZPN_SUBCAT value if no ZPN_SUBCAT parameter found",
            "validator": bool,
            "default": False,
        },
        "ZPN_SUBCAT_DEFVAL": {
            "name": "ZPN SUBCAT Default Value",
            "description": "Default ZPN_CAT value if no ZPN_CAT parameter found. Format is 2-digit code (default 00)",
            "default": "00",
            "validator": validate_ss,
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
        """Main plugin handler function for ZPN generation."""

        if not self.get_setting("ACTIVE"):
            return False

        id = kwargs.pop("id", None)
        model = kwargs.pop("model", None)

        # Events can fire on unrelated models
        if model != "Part":
            logger.debug("ZPN Generator: Event model is not Part")
            return

        # Fetch the part
        try:
            part = Part.objects.get(id=id)
        except Part.DoesNotExist:
            logger.warning(f"ZPN Generator: Part with id {id} not found")
            return

        # Don't create IPNs for parts that already have one
        if part.IPN:
            logger.debug(
                f"ZPN Generator: Part {id} already has IPN '{part.IPN}', skipping"
            )
            return

        # Attempt ZPN generation with retry for concurrency handling
        for attempt in range(1, ZPN_RETRY_ATTEMPTS + 1):
            try:
                new_ipn = generate_zpn_for_part(part)

                if not new_ipn:
                    # Generation failed due to missing/invalid parameters - already logged
                    return

                # Use atomic transaction for the save
                with transaction.atomic():
                    # Re-check current max to avoid race conditions
                    part.refresh_from_db()

                    # Double-check IPN hasn't been set in the meantime
                    if part.IPN:
                        logger.debug(
                            f"ZPN Generator: Part {id} IPN was set during processing, skipping"
                        )
                        return

                    # Recompute ZPN to get the latest sequence number
                    ccc = get_part_parameter_value(part, ZPN_CAT_PARAM)
                    ss = get_part_parameter_value(part, ZPN_SUBCAT_PARAM)

                    if ccc and ss:
                        ccc = ccc.strip().upper()
                        ss = ss.strip()
                        new_ipn = compute_next_zpn(ccc, ss)

                    part.IPN = new_ipn
                    part.save()

                logger.info(f"ZPN Generator: Assigned IPN '{new_ipn}' to Part {id}")
                return

            except IntegrityError as e:
                # Likely a uniqueness conflict - retry with new sequence
                logger.warning(
                    f"ZPN Generator: Integrity error on attempt {attempt}/{ZPN_RETRY_ATTEMPTS} "
                    f"for Part {id}: {e}"
                )
                if attempt == ZPN_RETRY_ATTEMPTS:
                    logger.error(
                        f"ZPN Generator: Failed to assign IPN to Part {id} after "
                        f"{ZPN_RETRY_ATTEMPTS} attempts due to integrity errors"
                    )
            except ValueError as e:
                # Sequence overflow
                logger.error(f"ZPN Generator: {e}")
                return
            except Exception as e:
                logger.error(
                    f"ZPN Generator: Unexpected error assigning IPN to Part {id}: {e}"
                )
                return

        return
