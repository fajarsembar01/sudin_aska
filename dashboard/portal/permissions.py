"""Permission helpers for admin role management."""

from typing import Dict, Any


def is_superadmin(user: Dict[str, Any]) -> bool:
    """
    Legacy helper: superadmin is now equivalent to admin.
    """
    return user.get("role") == "admin"


def is_viewer_admin(user: Dict[str, Any]) -> bool:
    """
    Check if user is a viewer admin (read-only).
    
    Args:
        user: Current user dict with role, admin_level fields
        
    Returns:
        True if user is admin with viewer level
    """
    return False


def can_access_aska(user: Dict[str, Any]) -> bool:
    """
    Check if user can access ASKA dashboard (not just Portal).
    
    Args:
        user: Current user dict with access_scope field
        
    Returns:
        True if user has full_access scope
    """
    return user.get("role") == "admin"


def can_edit_data(user: Dict[str, Any]) -> bool:
    """
    Check if user can edit/delete data (CRUD operations).
    
    Admins can edit data.
    
    Args:
        user: Current user dict
        
    Returns:
        True if user can perform edit/delete operations
    """
    return user.get("role") == "admin"


def can_assign_staff(user: Dict[str, Any]) -> bool:
    """
    Check if user can assign staff to schools.
    
    Args:
        user: Current user dict
        
    Returns:
        True if user can manage staff assignments
    """
    return user.get("role") == "admin"


def can_manage_periods(user: Dict[str, Any]) -> bool:
    """
    Check if user can create/edit assessment periods.
    
    Args:
        user: Current user dict
        
    Returns:
        True if user can manage periods
    """
    return user.get("role") == "admin"


def can_reopen_assessment(user: Dict[str, Any]) -> bool:
    """
    Check if user can reopen submitted assessments.
    
    Args:
        user: Current user dict
        
    Returns:
        True if user can reopen assessments
    """
    return user.get("role") == "admin"


def can_delete_assessment(user: Dict[str, Any]) -> bool:
    """
    Check if user can delete assessments.
    
    Args:
        user: Current user dict
        
    Returns:
        True if user can delete assessments
    """
    return user.get("role") == "admin"


def can_export_data(user: Dict[str, Any]) -> bool:
    """
    Check if user can export data.
    
    Admins can export data.
    
    Args:
        user: Current user dict
        
    Returns:
        True if user can export data
    """
    return user.get("role") == "admin"


def get_permission_summary(user: Dict[str, Any]) -> Dict[str, bool]:
    """
    Get a summary of all permissions for a user.
    
    Useful for debugging and UI conditional rendering.
    
    Args:
        user: Current user dict
        
    Returns:
        Dictionary of permission flags
    """
    return {
        "is_superadmin": is_superadmin(user),
        "is_viewer": is_viewer_admin(user),
        "can_access_aska": can_access_aska(user),
        "can_edit_data": can_edit_data(user),
        "can_assign_staff": can_assign_staff(user),
        "can_manage_periods": can_manage_periods(user),
        "can_reopen_assessment": can_reopen_assessment(user),
        "can_delete_assessment": can_delete_assessment(user),
        "can_export_data": can_export_data(user),
    }
