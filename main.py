from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse
from connector import connector
from classes import Login
from pymysql.cursors import DictCursor
from tokens import create_token, SECRET_KEY, ALGORITHM 
from decorators import jwt_required
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
from fastapi.staticfiles import StaticFiles
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
from datetime import datetime

app = FastAPI()

# Register Devanagari font - Add this at the top of your file, after imports
try:
    # Option 1: If you have Noto Sans Devanagari downloaded
    pdfmetrics.registerFont(TTFont('Devanagari', 'NotoSansDevanagari-Regular.ttf'))
    
    # Option 2: If on Windows with Mangal font
    # pdfmetrics.registerFont(TTFont('Devanagari', 'C:/Windows/Fonts/mangal.ttf'))
    
    # Option 3: If font is in a 'fonts' folder in your project
    # pdfmetrics.registerFont(TTFont('Devanagari', 'fonts/NotoSansDevanagari-Regular.ttf'))
    
    DEVANAGARI_FONT_AVAILABLE = True
except:
    DEVANAGARI_FONT_AVAILABLE = False
    print("Warning: Devanagari font not found. Marathi text may not display correctly.")


templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Register a font that supports Devanagari (you'll need to add this font file)
# For now, we'll use default fonts and transliterated text
# To properly display Marathi, download and register a Devanagari font like NotoSansDevanagari

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("new.html", {"request": request})


def convert_to_devanagari(text):
    """
    Convert English text to Devanagari (Marathi) script with multiple variations
    """
    variations = []
    
    try:
        devanagari = transliterate(text, sanscript.ITRANS, sanscript.DEVANAGARI)
        if devanagari.endswith('्'):
            devanagari = devanagari[:-1]
        variations.append(devanagari)
        
        devanagari_with_a = transliterate(text + 'a', sanscript.ITRANS, sanscript.DEVANAGARI)
        if devanagari_with_a.endswith('्'):
            devanagari_with_a = devanagari_with_a[:-1]
        if devanagari_with_a not in variations:
            variations.append(devanagari_with_a)
        
        text_lower = text.lower()
        
        if 'ksh' in text_lower or 'xh' in text_lower or 'ksa' in text_lower:
            alt_text = text_lower.replace('ksh', 'kSh').replace('xh', 'kSh').replace('ksa', 'kSh')
            alt = transliterate(alt_text, sanscript.ITRANS, sanscript.DEVANAGARI)
            if alt.endswith('्'):
                alt = alt[:-1]
            if alt not in variations:
                variations.append(alt)
        
        if 'sh' in text_lower:
            alt_text = text_lower.replace('sh', 'z')
            alt = transliterate(alt_text, sanscript.ITRANS, sanscript.DEVANAGARI)
            if alt.endswith('्'):
                alt = alt[:-1]
            if alt not in variations:
                variations.append(alt)
    
    except Exception as e:
        print(f"Transliteration error: {e}")
    
    if not variations:
        variations.append(text)
    
    return variations


def is_english(text):
    """Check if text contains English characters"""
    return any(ord(char) < 128 for char in text)


@app.post("/login")
def login(log:Login):
    try:
        conn = connector()
        cursor = conn.cursor(DictCursor)

        cursor.execute("SELECT * FROM USERS WHERE USER_NAME = %s AND PASSWORD = %s",(log.username, log.password))
        user = cursor.fetchone()
        if not user:
            return{
                "status":"Fail",
                "Message":"You Entered The Wrong Password Or Username"
            } 
        
        else:
            # Check if user is admin (you can define admin by user_name or add a new role column)
            is_admin = user["user_name"].lower() in ["admin", "sam"]  # Modify as needed
            
            token = create_token({"id":user["id"],"name":user["name"]})
            return{
                "status":"Success",
                "data":{
                    "id":user["id"],
                    "user":user["name"],
                    "User_Name":user["user_name"],
                    "is_admin": is_admin,
                    "token":token
                }
            }

    except Exception as e:
        print(e)
        return {
            "status": "Fail",
            "Message": "Server error"
        }


@app.get("/voters")
@jwt_required
def get_voters(request: Request, page: int = 1, limit: int = 20, search: str = None, id: str = None):
    offset = (page - 1) * limit

    conn = connector()
    cursor = conn.cursor(DictCursor)

    base_query = """
    SELECT 
        v.*, 
        vv.visited_by, 
        u.name AS visited_by_name,
        vv.visited_at
    FROM voters v
    LEFT JOIN voter_visits vv ON v.voter_id COLLATE utf8mb4_unicode_ci = vv.voter_id COLLATE utf8mb4_unicode_ci
    LEFT JOIN users u ON vv.visited_by = u.id
    """

    count_query = "SELECT COUNT(*) as total FROM voters v"

    if search and len(search.strip()) >= 3:
        search_term = search.strip()
        
        search_terms = [search_term]
        if is_english(search_term):
            devanagari_variations = convert_to_devanagari(search_term)
            search_terms.extend(devanagari_variations)
            print(f"English search: '{search_term}' -> Devanagari variations: {devanagari_variations}")
        
        search_conditions = []
        search_params_list = []
        
        for term in search_terms:
            prefix_pattern = f"{term}%"
            contains_pattern = f"%{term}%"
            word_boundary_pattern = f"% {term}%"
            
            search_conditions.append(
                "v.voter_id COLLATE utf8mb4_unicode_ci LIKE %s OR " +
                "v.voter_name COLLATE utf8mb4_unicode_ci LIKE %s OR " +
                "v.voter_name COLLATE utf8mb4_unicode_ci LIKE %s OR " +
                "v.voter_name_en COLLATE utf8mb4_unicode_ci LIKE %s OR " +
                "v.voter_name_en COLLATE utf8mb4_unicode_ci LIKE %s OR " +
                "v.voter_name_en COLLATE utf8mb4_unicode_ci LIKE %s"
            )
            search_params_list.extend([
                prefix_pattern, contains_pattern, word_boundary_pattern,
                prefix_pattern, contains_pattern, word_boundary_pattern
            ])
        
        full_search_condition = " WHERE (" + " OR ".join(search_conditions) + ")"
        
        base_query += full_search_condition
        count_query += full_search_condition
        
        search_params = tuple(search_params_list)
        
        cursor.execute(count_query, search_params)
        total_results = cursor.fetchone()["total"]
        
        base_query += " ORDER BY v.serial_no LIMIT %s OFFSET %s"
        cursor.execute(base_query, search_params + (limit, offset))
        
    else:
        cursor.execute(count_query)
        total_results = cursor.fetchone()["total"]
        
        base_query += " ORDER BY v.serial_no LIMIT %s OFFSET %s"
        cursor.execute(base_query, (limit, offset))

    data = cursor.fetchall()

    return {
        "status": "Success",
        "page": page,
        "total_results": total_results,
        "showing": len(data),
        "data": data,
        "search_query": search if search else None
    }


@app.post("/voters/{voter_id}/visit")
@jwt_required
def mark_visited(voter_id: str, request: Request, id: str = None):
    conn = connector()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO voter_visits (voter_id, visited_by)
            VALUES (%s, %s)
        """, (voter_id, id))

        conn.commit()
        return {
            "status": "Success",
            "message": "Voter marked as visited"
        }

    except Exception:
        return {
            "status": "Fail",
            "message": "Voter already visited"
        }
    

@app.get("/voters/stats")
@jwt_required
def voter_stats(request: Request, search: str = None, id: str = None):
    conn = connector()
    cursor = conn.cursor(DictCursor)

    search_condition = ""
    search_params = ()
    
    if search and len(search.strip()) >= 3:
        search_term = search.strip()
        
        search_terms = [search_term]
        if is_english(search_term):
            devanagari_variations = convert_to_devanagari(search_term)
            search_terms.extend(devanagari_variations)
        
        search_conditions = []
        search_params_list = []
        
        for term in search_terms:
            prefix_pattern = f"{term}%"
            contains_pattern = f"%{term}%"
            word_boundary_pattern = f"% {term}%"
            
            search_conditions.append(
                "v.voter_id COLLATE utf8mb4_unicode_ci LIKE %s OR " +
                "v.voter_name COLLATE utf8mb4_unicode_ci LIKE %s OR " +
                "v.voter_name COLLATE utf8mb4_unicode_ci LIKE %s"
            )
            search_params_list.extend([prefix_pattern, contains_pattern, word_boundary_pattern])
        
        search_condition = " WHERE (" + " OR ".join(search_conditions) + ")"
        search_params = tuple(search_params_list)

    cursor.execute(f"SELECT COUNT(*) AS total_voters FROM voters v {search_condition}", search_params)
    total_voters = cursor.fetchone()["total_voters"]

    if search_condition:
        cursor.execute(f"""
            SELECT COUNT(*) AS total_marked 
            FROM voter_visits vv
            JOIN voters v ON vv.voter_id COLLATE utf8mb4_unicode_ci = v.voter_id COLLATE utf8mb4_unicode_ci
            {search_condition}
        """, search_params)
    else:
        cursor.execute("SELECT COUNT(*) AS total_marked FROM voter_visits")
    
    total_marked = cursor.fetchone()["total_marked"]

    if search_condition:
        cursor.execute(f"""
            SELECT COUNT(*) AS marked_by_me 
            FROM voter_visits vv
            JOIN voters v ON vv.voter_id COLLATE utf8mb4_unicode_ci = v.voter_id COLLATE utf8mb4_unicode_ci
            {search_condition} AND vv.visited_by = %s
        """, search_params + (id,))
    else:
        cursor.execute(
            "SELECT COUNT(*) AS marked_by_me FROM voter_visits WHERE visited_by = %s",
            (id,)
        )
    
    marked_by_me = cursor.fetchone()["marked_by_me"]

    return {
        "status": "Success",
        "data": {
            "total_voters": total_voters,
            "total_marked": total_marked,
            "marked_by_me": marked_by_me
        }
    }


# ============== NEW ADMIN ENDPOINTS ==============

@app.get("/admin/user-wise-stats")
@jwt_required
def get_user_wise_stats(request: Request, id: str = None):
    """Get marking statistics for each user"""
    conn = connector()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT 
                u.id,
                u.name,
                u.user_name,
                COUNT(vv.id) as total_marked,
                MIN(vv.visited_at) as first_visit,
                MAX(vv.visited_at) as last_visit
            FROM users u
            LEFT JOIN voter_visits vv ON u.id = vv.visited_by
            GROUP BY u.id, u.name, u.user_name
            ORDER BY total_marked DESC
        """)
        
        user_stats = cursor.fetchall()
        
        return {
            "status": "Success",
            "data": user_stats
        }
        
    except Exception as e:
        print(e)
        return {
            "status": "Fail",
            "message": "Error fetching user statistics"
        }


@app.get("/admin/voters-full-list")
@jwt_required
def get_full_voters_list(request: Request, id: str = None):
    """Get complete voters list for PDF generation"""
    conn = connector()
    cursor = conn.cursor(DictCursor)
    
    try:
        cursor.execute("""
            SELECT 
                v.serial_no,
                v.voter_id,
                v.house_no,
                v.voter_name,
                v.voter_name_en,
                v.relative_name,
                v.age,
                v.gender,
                vv.visited_by,
                u.name AS visited_by_name,
                vv.visited_at
            FROM voters v
            LEFT JOIN voter_visits vv ON v.voter_id COLLATE utf8mb4_unicode_ci = vv.voter_id COLLATE utf8mb4_unicode_ci
            LEFT JOIN users u ON vv.visited_by = u.id
            ORDER BY v.serial_no
        """)
        
        voters = cursor.fetchall()
        
        return {
            "status": "Success",
            "total": len(voters),
            "data": voters
        }
        
    except Exception as e:
        print(e)
        return {
            "status": "Fail",
            "message": "Error fetching voters list"
        }


@app.get("/admin/download-pdf")
@jwt_required
def download_voters_pdf(request: Request, id: str = None):
    """Generate and download PDF of all voters with user statistics"""
    conn = connector()
    cursor = conn.cursor(DictCursor)
    
    try:
        # Get user-wise statistics
        cursor.execute("""
            SELECT 
                u.name,
                COUNT(vv.id) as total_marked
            FROM users u
            LEFT JOIN voter_visits vv ON u.id = vv.visited_by
            GROUP BY u.id, u.name
            HAVING total_marked > 0
            ORDER BY total_marked DESC
        """)
        user_stats = cursor.fetchall()
        
        # Get all voters
        cursor.execute("""
            SELECT 
                v.serial_no,
                v.voter_id,
                v.voter_name_en,
                v.voter_name,
                v.relative_name,
                v.age,
                v.gender,
                u.name AS visited_by_name
            FROM voters v
            LEFT JOIN voter_visits vv ON v.voter_id COLLATE utf8mb4_unicode_ci = vv.voter_id COLLATE utf8mb4_unicode_ci
            LEFT JOIN users u ON vv.visited_by = u.id
            ORDER BY v.serial_no
        """)
        
        voters = cursor.fetchall()
        
        # Create PDF in memory
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=30, bottomMargin=30)
        elements = []
        
        # Styles - Use Devanagari font where needed
        styles = getSampleStyleSheet()
        
        # Determine which font to use
        marathi_font = 'Devanagari' if DEVANAGARI_FONT_AVAILABLE else 'Helvetica'
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#2E7D32'),
            spaceAfter=20,
            alignment=1,  # Center
            fontName='Helvetica-Bold'
        )
        
        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#424242'),
            spaceAfter=15,
            alignment=1,
            fontName='Helvetica'
        )
        
        stats_header_style = ParagraphStyle(
            'StatsHeader',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1976D2'),
            spaceAfter=10,
            spaceBefore=10,
            fontName='Helvetica-Bold'
        )
        
        # Title
        title = Paragraph("Voter List Report", title_style)
        elements.append(title)
        
        # Date
        date_text = Paragraph(f"Generated on: {datetime.now().strftime('%d-%m-%Y %H:%M')}", subtitle_style)
        elements.append(date_text)
        elements.append(Spacer(1, 0.2*inch))
        
        # User Statistics Section
        stats_title = Paragraph("User-wise Marking Statistics", stats_header_style)
        elements.append(stats_title)
        
        # Create stats table
        stats_data = [['User Name', 'Voters Marked']]
        for stat in user_stats:
            stats_data.append([stat['name'], str(stat['total_marked'])])
        
        stats_table = Table(stats_data, colWidths=[4*inch, 2*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1976D2')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#E3F2FD')),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
        ]))
        
        elements.append(stats_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Voters List Section
        voters_title = Paragraph("Complete Voter List", stats_header_style)
        elements.append(voters_title)
        elements.append(Spacer(1, 0.1*inch))
        
        # Table data - Now with proper Marathi text support
        data = [['Sr No', 'Voter ID', 'Name (English)', 'Name (Marathi)', 'Relative Name', 'Age', 'Gender', 'Status']]
        
        for voter in voters:
            status = voter['visited_by_name'] if voter['visited_by_name'] else 'Not Visited'
            
            # Get gender in readable format
            gender_text = 'Male' if voter['gender'] in ['पु', 'M', 'Male'] else 'Female' if voter['gender'] in ['स्त्री', 'F', 'Female'] else voter['gender']
            
            # Use actual Marathi names from database
            marathi_name = voter['voter_name'] if voter['voter_name'] else voter['voter_name_en']
            relative_name = voter['relative_name'] if voter['relative_name'] else '-'
            
            data.append([
                str(voter['serial_no']),
                voter['voter_id'],
                voter['voter_name_en'],
                marathi_name,
                relative_name,
                str(voter['age']),
                gender_text,
                status
            ])
        
        # Create table with adjusted column widths
        table = Table(data, repeatRows=1, colWidths=[0.6*inch, 1.1*inch, 1.8*inch, 1.8*inch, 1.5*inch, 0.5*inch, 0.7*inch, 1.2*inch])
        
        # Table style with Devanagari font for Marathi columns
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4CAF50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]
        
        # Apply Devanagari font to Marathi name columns (columns 3 and 4)
        if DEVANAGARI_FONT_AVAILABLE:
            table_style.append(('FONTNAME', (3, 1), (3, -1), marathi_font))  # Name (Marathi) column
            table_style.append(('FONTNAME', (4, 1), (4, -1), marathi_font))  # Relative Name column
        
        table.setStyle(TableStyle(table_style))
        
        elements.append(table)
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=voters_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            }
        )
        
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Error generating PDF")