from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from classes import Login
from tokens import create_token
from decorators import jwt_required
from connector import connection_pool, get_db_connection, get_cursor

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from datetime import datetime
import io
import os


app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FONT_PATH = os.path.join(BASE_DIR, "fonts", "NotoSansDevanagari-Regular.ttf")

try:
    pdfmetrics.registerFont(TTFont("Devanagari", FONT_PATH))
    DEVANAGARI_FONT_AVAILABLE = True
except Exception:
    DEVANAGARI_FONT_AVAILABLE = False


templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup_event():
    connection_pool.initialize(
        host="localhost",
        user="sam",
        password="Sam@130201",
        database="election",
        charset="utf8mb4",
        autocommit=False,
    )


@app.on_event("shutdown")
async def shutdown_event():
    connection_pool.close_all()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("new.html", {"request": request})

@app.get("/user-voter-list", response_class=HTMLResponse)
def user_voter_list_page(request: Request):
    return templates.TemplateResponse("user_voter_list.html", {"request": request})


def normalize_name(text: str) -> str:
    return " ".join(sorted(text.lower().split())) if text else ""


def is_english(text: str) -> bool:
    return any(ord(c) < 128 for c in text)


def convert_to_devanagari(text: str):
    variations = []
    try:
        base = transliterate(text, sanscript.ITRANS, sanscript.DEVANAGARI)
        variations.append(base.rstrip("्"))
        with_a = transliterate(text + "a", sanscript.ITRANS, sanscript.DEVANAGARI)
        variations.append(with_a.rstrip("्"))
    except Exception:
        pass
    return list(set(variations)) or [text]


def calculate_relevance_score(search_term, voter_name, voter_name_en, voter_id):
    score = 0

    s = search_term.lower()
    n = (voter_name or "").lower()
    ne = (voter_name_en or "").lower()
    vid = (voter_id or "").lower()

    if s == n or s == ne:
        score += 1000

    if normalize_name(s) == normalize_name(ne):
        score += 800

    if s == vid:
        score += 900

    if ne.startswith(s) or n.startswith(s):
        score += 500

    if s in ne or s in n:
        score += 300

    if s in vid:
        score += 150

    return score


@app.post("/login")
def login(log: Login):
    with get_db_connection() as conn:
        cursor = get_cursor(conn, dict_cursor=True)
        cursor.execute(
            "SELECT * FROM users WHERE USER_NAME=%s AND PASSWORD=%s",
            (log.username, log.password),
        )
        user = cursor.fetchone()

        if not user:
            return {"status": "Fail", "Message": "Invalid credentials"}

        else:
            is_admin = user["user_name"].lower() in ["admin", "gite"]
            
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
        


# NEW API: GET ALL USERS LIST
@app.get("/admin/users")
@jwt_required
def get_users_list(request: Request, id: str = None):
    """Get list of all users for dropdown"""
    with get_db_connection() as conn:
        cursor = get_cursor(conn, dict_cursor=True)
        
        try:
            cursor.execute("""
                SELECT id, name, user_name
                FROM users
                ORDER BY name
            """)
            
            users = cursor.fetchall()
            
            return {
                "status": "Success",
                "data": users
            }
            
        except Exception as e:
            print(e)
            return {
                "status": "Fail",
                "message": "Error fetching users"
            }


# NEW API: GET VOTERS VISITED BY SPECIFIC USER
@app.get("/admin/user-voters/{user_id}")
@jwt_required
def get_user_voters(user_id: int, request: Request, id: str = None):
    """Get all voters visited by a specific user"""
    with get_db_connection() as conn:
        cursor = get_cursor(conn, dict_cursor=True)
        
        try:
            # Get user info
            cursor.execute("""
                SELECT name, user_name
                FROM users
                WHERE id = %s
            """, (user_id,))
            
            user_info = cursor.fetchone()
            
            if not user_info:
                return {
                    "status": "Fail",
                    "message": "User not found"
                }
            
            # Get voters visited by this user
            cursor.execute("""
                SELECT 
                    v.serial_no,
                    v.voter_id,
                    v.voter_name_en,
                    v.voter_name,
                    v.relative_name,
                    v.age,
                    v.gender,
                    vv.visited_at
                FROM voter_visits vv
                JOIN voters v ON vv.voter_id COLLATE utf8mb4_unicode_ci = v.voter_id COLLATE utf8mb4_unicode_ci
                WHERE vv.visited_by = %s
                ORDER BY vv.visited_at DESC
            """, (user_id,))
            
            voters = cursor.fetchall()
            
            return {
                "status": "Success",
                "data": {
                    "user_info": user_info,
                    "voters": voters,
                    "total_count": len(voters)
                }
            }
            
        except Exception as e:
            print(e)
            return {
                "status": "Fail",
                "message": "Error fetching user voters"
            }


# NEW API: DOWNLOAD PDF FOR SPECIFIC USER'S VISITED VOTERS
@app.get("/admin/download-user-pdf/{user_id}")
@jwt_required
def download_user_voters_pdf(user_id: int, request: Request, id: str = None):
    """Generate and download PDF of voters visited by specific user"""
    with get_db_connection() as conn:
        cursor = get_cursor(conn, dict_cursor=True)
        
        try:
            # Get user info
            cursor.execute("""
                SELECT name, user_name
                FROM users
                WHERE id = %s
            """, (user_id,))
            
            user_info = cursor.fetchone()
            
            if not user_info:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Get voters visited by this user
            cursor.execute("""
                SELECT 
                    v.serial_no,
                    v.voter_id,
                    v.voter_name_en,
                    v.voter_name,
                    v.relative_name,
                    v.age,
                    v.gender,
                    vv.visited_at
                FROM voter_visits vv
                JOIN voters v ON vv.voter_id COLLATE utf8mb4_unicode_ci = v.voter_id COLLATE utf8mb4_unicode_ci
                WHERE vv.visited_by = %s
                ORDER BY v.serial_no
            """, (user_id,))
            
            voters = cursor.fetchall()
            
            # Create PDF
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=30, bottomMargin=30)
            elements = []
            
            styles = getSampleStyleSheet()
            marathi_font = 'Devanagari' if DEVANAGARI_FONT_AVAILABLE else 'Helvetica'
            
            # Define styles
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                textColor=colors.HexColor('#2E7D32'),
                spaceAfter=20,
                alignment=1,
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
            
            user_info_style = ParagraphStyle(
                'UserInfo',
                parent=styles['Normal'],
                fontSize=14,
                textColor=colors.HexColor('#1976D2'),
                spaceAfter=10,
                alignment=1,
                fontName='Helvetica-Bold'
            )
            
            # Add title
            title = Paragraph("Voter Visit Report", title_style)
            elements.append(title)
            
            # Add user info
            user_text = Paragraph(
                f"User: {user_info['name']} ({user_info['user_name']})", 
                user_info_style
            )
            elements.append(user_text)
            
            # Add generation date
            date_text = Paragraph(
                f"Generated on: {datetime.now().strftime('%d-%m-%Y %H:%M')}", 
                subtitle_style
            )
            elements.append(date_text)
            
            # Add total count
            count_text = Paragraph(
                f"Total Voters Visited: {len(voters)}", 
                subtitle_style
            )
            elements.append(count_text)
            
            elements.append(Spacer(1, 0.3*inch))
            
            # Create table data
            data = [[
                'Sr No', 'Voter ID', 'Name (English)', 'Name (Marathi)', 
                'Relative Name', 'Age', 'Gender', 'Visited On'
            ]]
            
            for voter in voters:
                gender_text = (
                    'Male' if voter['gender'] in ['पु', 'M', 'Male'] 
                    else 'Female' if voter['gender'] in ['स्त्री', 'F', 'Female'] 
                    else voter['gender']
                )
                marathi_name = voter['voter_name'] if voter['voter_name'] else voter['voter_name_en']
                relative_name = voter['relative_name'] if voter['relative_name'] else '-'
                visited_date = voter['visited_at'].strftime('%d-%m-%Y') if voter['visited_at'] else '-'
                
                data.append([
                    str(voter['serial_no']),
                    voter['voter_id'],
                    voter['voter_name_en'],
                    marathi_name,
                    relative_name,
                    str(voter['age']),
                    gender_text,
                    visited_date
                ])
            
            # Create table
            table = Table(
                data, 
                repeatRows=1, 
                colWidths=[0.6*inch, 1.1*inch, 1.8*inch, 1.8*inch, 1.5*inch, 0.5*inch, 0.7*inch, 1.0*inch]
            )
            
            # Table styling
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
            
            # Add Devanagari font if available
            if DEVANAGARI_FONT_AVAILABLE:
                table_style.append(('FONTNAME', (3, 1), (3, -1), marathi_font))
                table_style.append(('FONTNAME', (4, 1), (4, -1), marathi_font))
            
            table.setStyle(TableStyle(table_style))
            
            elements.append(table)
            
            # Build PDF
            doc.build(elements)
            buffer.seek(0)
            
            # Create filename
            filename = f"user_{user_info['user_name']}_voters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            return StreamingResponse(
                buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                }
            )
            
        except Exception as e:
            print(e)
            raise HTTPException(status_code=500, detail="Error generating PDF")


@app.get("/voters")
@jwt_required
def get_voters(request: Request, page: int = 1, limit: int = 20, search: str = None, id: str = None):
    offset = (page - 1) * limit

    with get_db_connection() as conn:
        cursor = get_cursor(conn, dict_cursor=True)

        base_query = """
            SELECT v.*, vv.visited_by, u.name AS visited_by_name, vv.visited_at
            FROM voters v
            LEFT JOIN voter_visits vv
              ON v.voter_id COLLATE utf8mb4_unicode_ci =
                 vv.voter_id COLLATE utf8mb4_unicode_ci
            LEFT JOIN users u ON vv.visited_by = u.id
        """

        count_query = "SELECT COUNT(*) AS total FROM voters v"

        if search and len(search.strip()) >= 3:
            search_term = search.strip()
            words = search_term.lower().split()
            reversed_search = " ".join(reversed(words))

            search_terms = [search_term]
            if is_english(search_term):
                search_terms.extend(convert_to_devanagari(search_term))

            conditions = []
            params = []

            for term in search_terms:
                conditions.append("""
                    (
                        v.voter_id LIKE %s OR
                        v.voter_name LIKE %s OR
                        v.voter_name LIKE %s OR
                        v.voter_name_en LIKE %s OR
                        v.voter_name_en LIKE %s OR
                        CONCAT_WS(' ', v.voter_name_en) LIKE %s OR
                        CONCAT_WS(' ', v.voter_name_en) LIKE %s
                    )
                """)
                params.extend([
                    f"%{term}%",
                    f"%{term}%",
                    f"% {term}%",
                    f"%{term}%",
                    f"% {term}%",
                    f"%{search_term}%",
                    f"%{reversed_search}%",
                ])

            where = " WHERE " + " OR ".join(conditions)
            base_query += where
            count_query += where

            cursor.execute(count_query, tuple(params))
            total_results = cursor.fetchone()["total"]

            base_query += " ORDER BY v.serial_no LIMIT 500"
            cursor.execute(base_query, tuple(params))
            rows = cursor.fetchall()

            scored = [
                {"score": calculate_relevance_score(search_term, r["voter_name"], r["voter_name_en"], r["voter_id"]), "data": r}
                for r in rows
            ]

            scored.sort(key=lambda x: x["score"], reverse=True)
            data = [x["data"] for x in scored[offset: offset + limit]]

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
            "search_query": search,
        }



@app.post("/voters/{voter_id}/visit")
@jwt_required
def mark_visited(voter_id: str, request: Request, id: str = None):
    with get_db_connection() as conn:
        cursor = get_cursor(conn, dict_cursor=False)

        try:
            cursor.execute("""
                INSERT INTO voter_visits (voter_id, visited_by)
                VALUES (%s, %s)
            """, (voter_id, id))

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
    with get_db_connection() as conn:
        cursor = get_cursor(conn, dict_cursor=True)

        search_condition = ""
        search_params = ()
        
        if search and len(search.strip()) >= 3:
            search_term = search.strip()
            
            search_terms = [search_term]
            if is_english(search_term):
                devanagari_variations = convert_to_devanagari(search_term)
                search_terms.extend(devanagari_variations)
            
            search_words = search_term.split()
            
            search_conditions = []
            search_params_list = []
            
            for term in search_terms:
                prefix_pattern = f"{term}%"
                contains_pattern = f"%{term}%"
                word_boundary_pattern = f"% {term}%"
                
                search_conditions.append(
                    "(v.voter_id COLLATE utf8mb4_unicode_ci LIKE %s OR " +
                    "v.voter_name COLLATE utf8mb4_unicode_ci LIKE %s OR " +
                    "v.voter_name COLLATE utf8mb4_unicode_ci LIKE %s OR " +
                    "v.voter_name_en COLLATE utf8mb4_unicode_ci LIKE %s)"
                )
                search_params_list.extend([prefix_pattern, contains_pattern, word_boundary_pattern, contains_pattern])
            
            for word in search_words:
                if len(word) >= 2:
                    word_pattern = f"%{word}%"
                    search_conditions.append(
                        "(v.voter_name COLLATE utf8mb4_unicode_ci LIKE %s OR " +
                        "v.voter_name_en COLLATE utf8mb4_unicode_ci LIKE %s)"
                    )
                    search_params_list.extend([word_pattern, word_pattern])
            
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


@app.get("/admin/user-wise-stats")
@jwt_required
def get_user_wise_stats(request: Request, id: str = None):
    """Get marking statistics for each user"""
    with get_db_connection() as conn:
        cursor = get_cursor(conn, dict_cursor=True)
        
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


@app.get("/admin/download-pdf")
@jwt_required
def download_voters_pdf(request: Request, id: str = None):
    """Generate and download PDF of all voters with user statistics"""
    with get_db_connection() as conn:
        cursor = get_cursor(conn, dict_cursor=True)
        
        try:
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
            
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=30, bottomMargin=30)
            elements = []
            
            styles = getSampleStyleSheet()
            marathi_font = 'Devanagari' if DEVANAGARI_FONT_AVAILABLE else 'Helvetica'
            
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                textColor=colors.HexColor('#2E7D32'),
                spaceAfter=20,
                alignment=1,
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
            
            title = Paragraph("Voter List Report", title_style)
            elements.append(title)
            
            date_text = Paragraph(f"Generated on: {datetime.now().strftime('%d-%m-%Y %H:%M')}", subtitle_style)
            elements.append(date_text)
            elements.append(Spacer(1, 0.2*inch))
            
            stats_title = Paragraph("User-wise Marking Statistics", stats_header_style)
            elements.append(stats_title)
            
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
            
            voters_title = Paragraph("Complete Voter List", stats_header_style)
            elements.append(voters_title)
            elements.append(Spacer(1, 0.1*inch))
            
            data = [['Sr No', 'Voter ID', 'Name (English)', 'Name (Marathi)', 'Relative Name', 'Age', 'Gender', 'Status']]
            
            for voter in voters:
                status = voter['visited_by_name'] if voter['visited_by_name'] else 'Not Visited'
                gender_text = 'Male' if voter['gender'] in ['पु', 'M', 'Male'] else 'Female' if voter['gender'] in ['स्त्री', 'F', 'Female'] else voter['gender']
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
            
            table = Table(data, repeatRows=1, colWidths=[0.6*inch, 1.1*inch, 1.8*inch, 1.8*inch, 1.5*inch, 0.5*inch, 0.7*inch, 1.2*inch])
            
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
            
            if DEVANAGARI_FONT_AVAILABLE:
                table_style.append(('FONTNAME', (3, 1), (3, -1), marathi_font))
                table_style.append(('FONTNAME', (4, 1), (4, -1), marathi_font))
            
            table.setStyle(TableStyle(table_style))
            
            elements.append(table)
            
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

