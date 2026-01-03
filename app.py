from fastapi import FastAPI, Request, Depends, HTTPException
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


app = FastAPI()

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("new.html", {"request": request})


def convert_to_devanagari(text):
    """
    Convert English text to Devanagari (Marathi) script with multiple variations
    Example: "akshay" -> ["अक्षय", "अक्शय", "आक्षय", etc.]
    """
    variations = []
    
    try:
        # Method 1: ITRANS transliteration
        devanagari = transliterate(text, sanscript.ITRANS, sanscript.DEVANAGARI)
        if devanagari.endswith('्'):
            devanagari = devanagari[:-1]
        variations.append(devanagari)
        
        # Method 2: Try with vowel at end
        devanagari_with_a = transliterate(text + 'a', sanscript.ITRANS, sanscript.DEVANAGARI)
        if devanagari_with_a.endswith('्'):
            devanagari_with_a = devanagari_with_a[:-1]
        if devanagari_with_a not in variations:
            variations.append(devanagari_with_a)
        
        # Method 3: Common spelling variations for specific patterns
        text_lower = text.lower()
        
        # Handle 'ksh' -> 'क्ष'
        if 'ksh' in text_lower or 'xh' in text_lower or 'ksa' in text_lower:
            alt_text = text_lower.replace('ksh', 'kSh').replace('xh', 'kSh').replace('ksa', 'kSh')
            alt = transliterate(alt_text, sanscript.ITRANS, sanscript.DEVANAGARI)
            if alt.endswith('्'):
                alt = alt[:-1]
            if alt not in variations:
                variations.append(alt)
        
        # Handle 'sh' -> 'श'
        if 'sh' in text_lower:
            alt_text = text_lower.replace('sh', 'z')
            alt = transliterate(alt_text, sanscript.ITRANS, sanscript.DEVANAGARI)
            if alt.endswith('्'):
                alt = alt[:-1]
            if alt not in variations:
                variations.append(alt)
    
    except Exception as e:
        print(f"Transliteration error: {e}")
    
    # If no variations found, return the original text
    if not variations:
        variations.append(text)
    
    return variations


def is_english(text):
    """
    Check if text contains English characters
    """
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
            token = create_token({"id":user["id"],"name":user["name"]})
            return{
                "status":"Success",
                "data":{
                    "id":user["id"],
                    "user":user["name"],
                    "User_Name":user["user_name"],
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

    # Base query with COLLATE to fix charset mismatch
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

    # Count query for total results
    count_query = "SELECT COUNT(*) as total FROM voters v"

    # Add search conditions if search parameter exists
    if search and len(search.strip()) >= 3:
        search_term = search.strip()
        
        # If search is in English, convert to Devanagari with multiple variations
        search_terms = [search_term]
        if is_english(search_term):
            devanagari_variations = convert_to_devanagari(search_term)
            search_terms.extend(devanagari_variations)
            print(f"English search: '{search_term}' -> Devanagari variations: {devanagari_variations}")
        
        # Build search conditions - Fixed SQL syntax
        search_conditions = []
        search_params_list = []
        
        for term in search_terms:
            prefix_pattern = f"{term}%"
            contains_pattern = f"%{term}%"
            word_boundary_pattern = f"% {term}%"
            
            # Search in voter_id, voter_name (Marathi), and voter_name_english
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
        
        # Join all conditions with OR
        full_search_condition = " WHERE (" + " OR ".join(search_conditions) + ")"
        
        base_query += full_search_condition
        count_query += full_search_condition
        
        search_params = tuple(search_params_list)
        
        # Get total count for search results
        cursor.execute(count_query, search_params)
        total_results = cursor.fetchone()["total"]
        
        # Add ordering and pagination
        base_query += " ORDER BY v.serial_no LIMIT %s OFFSET %s"
        cursor.execute(base_query, search_params + (limit, offset))
        
    else:
        # No search - normal pagination
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

    # If search is active, show stats for search results
    search_condition = ""
    search_params = ()
    
    if search and len(search.strip()) >= 3:
        search_term = search.strip()
        
        # If search is in English, convert to Devanagari with multiple variations
        search_terms = [search_term]
        if is_english(search_term):
            devanagari_variations = convert_to_devanagari(search_term)
            search_terms.extend(devanagari_variations)
        
        # Build search conditions - Fixed SQL syntax
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

    # Total voters (with or without search filter)
    cursor.execute(f"SELECT COUNT(*) AS total_voters FROM voters v {search_condition}", search_params)
    total_voters = cursor.fetchone()["total_voters"]

    # Total marked voters (with or without search filter)
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

    # Marked by logged-in user (with or without search filter)
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
