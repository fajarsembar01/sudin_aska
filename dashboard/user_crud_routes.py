"""
User CRUD API endpoints - Add to dashboard/routes.py
"""

@main_bp.route('/users/<int:user_id>', methods=['GET'])
@role_required('admin')  
def get_user_api(user_id: int) -> Response:
    """Get user data for editing"""
    from dashboard.db_access import get_cursor
    
    with get_cursor() as cur:
        cur.execute("""
            SELECT u.*, k.name as kecamatan_name
            FROM dashboard_users u
            LEFT JOIN portal_kecamatan k ON u.requested_kecamatan = k.id
            WHERE u.id = %s
        """, (user_id,))
        user = cur.fetchone()
    
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
    return jsonify({'success': True, 'user': dict(user)})


@main_bp.route('/users/<int:user_id>', methods=['PUT'])
@role_required('admin')
def update_user_api(user_id: int) -> Response:
    """Update existing user"""
    from dashboard.db_access import get_cursor
    from werkzeug.security import generate_password_hash
    
    data = request.get_json()
    fields = []
    values = []
    
    if data.get('full_name'):
        fields.append('full_name = %s')
        values.append(data['full_name'])
    if data.get('email'):
        fields.append('email = %s')
        values.append(data['email'])
    if data.get('role'):
        fields.append('role = %s')
        values.append(data['role'])
    if data.get('admin_level'):
        fields.append('admin_level = %s')
        values.append(data['admin_level'])
    if data.get('access_scope'):
        fields.append('access_scope = %s')
        values.append(data['access_scope'])
    if data.get('password'):
        password_hash = generate_password_hash(data['password'], method="pbkdf2:sha256")
        fields.append('password_hash = %s')
        values.append(password_hash)
    
    if not fields:
        return jsonify({'success': False, 'message': 'No fields to update'}), 400
    
    values.append(user_id)
    query = f"UPDATE dashboard_users SET {', '.join(fields)} WHERE id = %s"
    
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(query, values)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@main_bp.route('/users/<int:user_id>', methods=['DELETE'])
@role_required('admin')
def delete_user_api(user_id: int) -> Response:
    """Delete user"""
    from dashboard.db_access import get_cursor
    
    current = current_user()
    if current and current.get('id') == user_id:
        return jsonify({'success': False, 'message': 'Cannot delete yourself'}), 400
    
    try:
        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM dashboard_users WHERE id = %s", (user_id,))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
