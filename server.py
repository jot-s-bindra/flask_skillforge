from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

class ERPClient:
    def __init__(self, base_url: str = "https://erp.iiita.ac.in"):
        self.base_url = base_url
        self.session = requests.Session()

    def login(self, credentials):
        """Logs in to ERP and returns True if successful, False otherwise"""
        try:
            response = self.session.post(
                self.base_url,
                data=credentials,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            return "Welcome" in response.text
        except requests.RequestException as e:
            print(f"Login failed: {e}")
            return False

    def get_all_courses(self, html_content):
        """Parses ERP HTML and extracts course details"""
        soup = BeautifulSoup(html_content, 'html.parser')
        courses = []
        
        semester_sections = soup.find_all('fieldset')
        for section in semester_sections:
            legend = section.find('legend')
            if not legend or 'Semester' not in legend.text:
                continue
                
            sem_match = re.search(r'Semester \[ (\d+) \]', legend.text)
            if not sem_match:
                continue
            semester = int(sem_match.group(1))
            
            table = section.find('table', {'class': 'interface2'})
            if not table:
                continue
                
            rows = table.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 15:
                    continue
                    
                title = row.get('title', '')
                faculty_match = re.search(r'Faculty: ([^)]+)', title)
                reg_date_match = re.search(r'Registration Date: (\d{2}-\d{2}-\d{4})', title)
                section_match = re.search(r'Sec\.([A-D])', cols[6].text.strip())

                course_dict = {
                    "semester": semester,
                    "course_name": cols[1].text.strip(),
                    "course_code": cols[2].text.strip(),
                    "course_type": cols[3].text.strip(),
                    "credits": cols[4].text.strip(),
                    "faculty": faculty_match.group(1) if faculty_match else None,
                    "registration_date": reg_date_match.group(1) if reg_date_match else None,
                    "attendance": cols[6].text.strip().split('sup')[0],
                    "section": section_match.group(1) if section_match else None,
                    "marks": {
                        "mid_sem": cols[7].text.strip(),
                        "internal": cols[8].text.strip(),
                        "end_sem": cols[9].text.strip(),
                        "back1": cols[10].text.strip(),
                        "back2": cols[11].text.strip(),
                        "total": cols[12].text.strip()
                    },
                    "grade": cols[13].text.strip(),
                    "result": cols[15].text.strip()
                }
                courses.append(course_dict)
                
        return courses

    def get_semester_summary(self, html_content):
        """Extracts semester summary (SGPA, CGPA, credits)"""
        soup = BeautifulSoup(html_content, 'html.parser')
        summaries = {}
        
        semester_sections = soup.find_all('fieldset')
        for section in semester_sections:
            legend = section.find('legend')
            if not legend or 'Semester' not in legend.text:
                continue
                
            sem_match = re.search(r'Semester \[ (\d+) \]', legend.text)
            if not sem_match:
                continue
            semester = sem_match.group(1)
            
            table = section.find('table', {'class': 'interface2'})
            if not table:
                continue
                
            summary_row = table.find_all('tr')[-1]
            if 'Summary' not in summary_row.text:
                continue
                
            cols = summary_row.find_all('th')
            summaries[semester] = {
                'credits': cols[4].text.strip() if len(cols) > 4 else 'N/A',
                'sgpa': cols[-3].text.strip() if len(cols) > 3 else 'N/A',
                'cgpa': cols[-1].text.strip() if len(cols) > 1 else 'N/A'
            }
            
        return summaries


@app.route('/api/student/details', methods=['POST'])
def get_student_details():
    try:
        data = request.get_json()

        required_fields = ['uid', 'pwd', 'batch']
        if not all(field in data for field in required_fields):
            return jsonify({
                "error": "Missing required fields",
                "required_fields": required_fields
            }), 400

        client = ERPClient()

        credentials = {
            'myBatch': data['batch'],
            'uid': data['uid'],
            'pwd': data['pwd'],
            'norobo': "1"
        }

        if not client.login(credentials):
            return jsonify({
                "error": "Login failed",
                "message": "Invalid credentials or connection error"
            }), 401

        response = client.session.get(client.base_url)

        # Get full course details
        courses = client.get_all_courses(response.text)
        summaries = client.get_semester_summary(response.text)

        # Simplify the response
        semester_data = {}

        for course in courses:
            semester = course["semester"]
            if semester not in semester_data:
                semester_data[semester] = {
                    "semester": semester,
                    "cgpa": summaries.get(str(semester), {}).get("cgpa", "N/A"),
                    "courses": []
                }

            semester_data[semester]["courses"].append({
                "course_name": course["course_name"],
                "course_code": course["course_code"],
                "grade": course["grade"]
            })

        return jsonify({
            "status": "success",
            "data": {
                "semesters": list(semester_data.values())
            }
        })

    except requests.RequestException as e:
        return jsonify({"error": "Connection error", "message": str(e)}), 500

    except Exception as e:
        return jsonify({"error": "Server error", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5112)
