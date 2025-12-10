
def get_portal_schools_paginated(
    page: int = 1,
    per_page: int = 20,
    search: Optional[str] = None,
    jenjang: Optional[str] = None,
    active_only: bool = True,
) -> Dict[str, Any]:
    """Fetch paginated schools."""
    conditions = []
    params = []
    
    if active_only:
        conditions.append("s.active = TRUE")
    
    if jenjang:
        conditions.append("s.jenjang = %s")
        params.append(jenjang)
    
    if search:
        conditions.append("(s.name ILIKE %s OR s.npsn ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    # 1. Get total count
    count_query = f"""
        SELECT COUNT(*) as total
        FROM portal_schools s
        LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
        LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
        {where_clause}
    """
    
    items = []
    total = 0
    pages = 0
    
    with get_cursor() as cur:
        cur.execute(count_query, params)
        total = cur.fetchone()["total"]
        
        import math
        pages = math.ceil(total / per_page)
        
        if page > pages and pages > 0:
            page = pages
        if page < 1:
            page = 1
            
        offset = (page - 1) * per_page
        
        # 2. Get items
        query = f"""
            SELECT 
                s.id, s.npsn, s.name, s.jenjang, s.alamat, s.status,
                s.kelurahan_id, s.user_id, s.active, s.created_at,
                l.name as kelurahan_name,
                k.name as kecamatan_name
            FROM portal_schools s
            LEFT JOIN portal_kelurahan l ON s.kelurahan_id = l.id
            LEFT JOIN portal_kecamatan k ON l.kecamatan_id = k.id
            {where_clause}
            ORDER BY k.name, l.name, s.jenjang, s.name
            LIMIT %s OFFSET %s
        """
        
        # Add LIMIT/OFFSET params
        query_params = params + [per_page, offset]
        
        cur.execute(query, query_params)
        items = [dict(row) for row in cur.fetchall()]
        
    return {
        "items": items,
        "total": total,
        "pages": pages,
        "current_page": page, 
        "per_page": per_page
    }
