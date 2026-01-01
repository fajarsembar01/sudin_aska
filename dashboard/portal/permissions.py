"""Permission helpers for admin role management."""

from typing import Dict, Any


def is_superadmin(user: Dict[str, Any]) -> bool:
    """
    Check if user is a superadmin with full CRUD access.
    
    Args:
        user: Current user dict with role, admin_level fields
        
    Returns:
        True if user is admin with superadmin level
    """
    return user.get("role") == "admin" and user.get("admin_level") == "superadmin"


def is_viewer_admin(user: Dict[str, Any]) -> bool:
    """
    Check if user is a viewer admin (read-only).
    
    Args:
        user: Current user dict with role, admin_level fields
        
    Returns:
        True if user is admin with viewer level
    """
    return user.get("role") == "admin" and user.get("admin_level") == "viewer"


def can_access_aska(user: Dict[str, Any]) -> bool:
    """
    Check if user can access ASKA dashboard (not just Portal).
    
    Args:
        user: Current user dict with access_scope field
        
    Returns:
        True if user has full_access scope
    """
    return user.get("access_scope") == "full_access"


def can_edit_data(user: Dict[str, Any]) -> bool:
    """
    Check if user can edit/delete data (CRUD operations).
    
    Only superadmins can edit data. Viewer admins are read-only.
    
    Args:
        user: Current user dict
        
    Returns:
        True if user can perform edit/delete operations
    """
    return is_superadmin(user)


def can_assign_staff(user: Dict[str, Any]) -> bool:
    """
    Check if user can assign staff to schools.
    
    Args:
        user: Current user dict
        
    Returns:
        True if user can manage staff assignments
    """
    return is_superadmin(user)


def can_manage_periods(user: Dict[str, Any]) -> bool:
    """
    Check if user can create/edit assessment periods.
    
    Args:
        user: Current user dict
        
    Returns:
        True if user can manage periods
    """
    return is_superadmin(user)


def can_reopen_assessment(user: Dict[str, Any]) -> bool:
    """
    Check if user can reopen submitted assessments.
    
    Args:
        user: Current user dict
        
    Returns:
        True if user can reopen assessments
    """
    return is_superadmin(user)


def can_delete_assessment(user: Dict[str, Any]) -> bool:
    """
    Check if user can delete assessments.
    
    Args:
        user: Current user dict
        
    Returns:
        True if user can delete assessments
    """
    return is_superadmin(user)


def can_export_data(user: Dict[str, Any]) -> bool:
    """
    Check if user can export data.
    
    Both superadmin and viewer can export, but viewer only gets
    data from their assigned kecamatans.
    
    Args:
        user: Current user dict
        
    Returns:
        True if user can export data
    """
    return user.get("role") == "admin"  # Both superadmin and viewer


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
