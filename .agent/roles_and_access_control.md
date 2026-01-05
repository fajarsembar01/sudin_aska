# Roles and Access Control - ASKA Portal

**Last Updated**: 2025-12-30
**Version**: 2.0 (Simplified System)

---

## Overview

ASKA Portal uses a **simplified role-based access control system** with clear hierarchy based on organizational structure. The system consists of 4 main roles with distinct permissions and access levels.

---

## User Roles

### 1. Admin
**Who**: Kasudin, Kasubag, IT Staff
**Access Level**: Full system access

**Permissions**:
- ✅ Full access to ASKA Insight
- ✅ Full access to Portal (all sections)
- ✅ Team Management (assign coordinators and staff)
- ✅ User Management (CRUD operations)
- ✅ Statistics and reporting (all data)
- ✅ Setup and configuration

**Login Flow**: `Login → /admin/select-role → Choose "ASKA Insight" or "Portal"`

---

### 2. Coordinator
**Who**: Kepala Seksi, Kasatlak, Penilik
**Access Level**: Section/team management

**Organizational Sections**:
1. PAUD & PMPK
2. SD  
3. SMP & SMA
4. SMK, Kursus & Pelatihan
5. PTK

**Permissions**:
- ✅ View own section dashboard
- ✅ View team members and statistics
- ✅ Contact team members
- ❌ Cannot assign/remove staff
- ❌ Cannot access ASKA Insight

**Login Flow**: `Login → /portal/coordinator/dashboard (automatic)`

---

### 3. Staff
**Who**: Field workers, Pemantau
**Access Level**: Own work only

**Permissions**:
- ✅ View own assignments
- ✅ Create/submit assessments
- ❌ Cannot view other staff's work

**Login Flow**: `Login → /portal/ (staff home)`

---

### 4. Sekolah
**Who**: School accounts
**Access Level**: Own school data only

**Permissions**:
- ✅ Configure own school only
- ❌ Cannot view other schools

**Login Flow**: `Login → /portal/sekolah/rooms`

---

## Permission Matrix

| Feature | Admin | Coordinator | Staff | Sekolah |
|---------|-------|-------------|-------|---------|
| ASKA Insight | ✅ Full | ❌ | ❌ | ❌ |
| Portal Statistics | ✅ All | ✅ Own Section | ❌ | ❌ |
| Team Management | ✅ Full | ❌ | ❌ | ❌ |
| Coordinator Dashboard | ✅ View All | ✅ Own Team | ❌ | ❌ |
| User Management | ✅ CRUD | ❌ | ❌ | ❌ |
| Create Assessment | ✅ Any | ✅ Assigned | ✅ Assigned | ❌ |
| School Config | ✅ All | ❌ | ❌ | ✅ Own |

---

## Database Schema

**sections**:
```sql
id, name, description, coordinator_id, created_at, updated_at
```

**dashboard_users** (team fields):
```sql
role VARCHAR  -- 'admin', 'coordinator', 'staff', 'sekolah'
section_id INT  -- Section membership
supervisor_id INT  -- Direct supervisor
```

**REMOVED** (v2.0):
- ❌ `admin_level` 
- ❌ `access_scope`

---

## Common Workflows

### Admin: Assign Team
1. Login → Admin → Team Management
2. Assign Coordinator: Select section → Choose user
3. Assign Staff: Select section + supervisor → Assign user

### Coordinator: Manage Team
1. Login → Auto-redirect to Dashboard
2. View team stats and member list
3. Contact via WhatsApp links

### Staff: Create Assessment
1. Login → Staff Home
2. "Tugas Monev" → Select school → Create assessment

---

## Implementation

**Auth Decorator**: `@role_required("admin", "coordinator")`

**Login Redirect**:
```python
if role == "admin": return "admin_select_role"
elif role == "coordinator": return "coordinator_dashboard"
elif role == "staff": return "portal.home"
elif role == "sekolah": return "sekolah_rooms"
```

**Portal Access**: `@_portal_access_required` allows admin/coordinator/staff/sekolah

---

## Migration from v1.x

**Old**: `admin_level` + `access_scope` = complex
**New**: Simple 4 roles + section hierarchy

**Changes**:
1. ✅ Created sections table
2. ✅ Added section_id, supervisor_id
3. ✅ Dropped admin_level, access_scope
4. ✅ Simplified auth decorators
5. ✅ Added team management UI

---

**Status**: Production Ready ✅
**Documentation Version**: 2.0
