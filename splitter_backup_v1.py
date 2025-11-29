import re
import os
import yaml # تأكد من تثبيتها: pip install pyyaml

# --- توابع مساعدة ---

def clean_text(text):
    """تنظيف النص وإزالة المسافات البيضاء الزائدة"""
    return text.strip()

def generate_slug(title):
    """توليد Slug (معرّف مسار) من العنوان باللغة العربية"""
    # يزيل الأحرف غير اللاتينية/العربية/الأرقام/المسافات
    slug = re.sub(r'[^\w\s-]', '', title)
    # يستبدل المسافات بشرطة سفلية ويحذف الشرطات السفلية الزائدة من الأطراف
    slug = re.sub(r'[\s]+', '_', slug).strip('_')
    return slug

def parse_legislation_card(content):
    """استخراج البيانات من قسم بطاقة التشريع لملء الـ YAML"""
    metadata = {
        "type": "نظام",
        "status": "ساري",
        "issuance_date": "",
        "articles_count": ""
    }
    
    # البحث عن القيم في النص
    type_match = re.search(r'- \*\*النوع\*\*: (.*)', content)
    if type_match: metadata['type'] = type_match.group(1).strip()

    status_match = re.search(r'- \*\*الحالة\*\*: (.*)', content)
    if status_match: metadata['status'] = status_match.group(1).strip()
    
    # محاولة استخراج التاريخ الهجري أو الميلادي قبل كلمة "الموافق"
    date_match = re.search(r'- \*\*التاريخ\*\*: (.*) الموافق', content)
    if date_match: metadata['issuance_date'] = date_match.group(1).strip().split(' ')[0]
    
    return metadata

def create_yaml_header(data):
    """إنشاء رأس YAML بتنسيق صحيح"""
    return "---\n" + yaml.dump(data, allow_unicode=True, sort_keys=False) + "---\n"

# --- الوظيفة الرئيسية لمعالجة الملف الواحد ---

def process_file_pure_python(file_path, output_dir):
    
    # 1. قراءة المحتوى
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 2. تحديد اسم النظام (Slug) والميتاداتا
    # نستخدم أول سطر (عنوان H1) لتحديد الاسم بدلاً من اسم الملف الفعلي
    title_match = re.search(r'^#\s*(.+)', content, re.MULTILINE)
    if title_match:
        raw_title = title_match.group(1).strip()
        doc_slug = "وثيقة-" + generate_slug(raw_title) 
    else:
        # إذا لم نجد عنوان H1، نعتمد على اسم الملف
        raw_title = os.path.basename(file_path).replace('.md', '')
        doc_slug = "وثيقة-" + generate_slug(raw_title)

    metadata = parse_legislation_card(content)
    metadata['doc'] = doc_slug
    metadata['domain'] = "تجاري" 

    # 3. تقسيم المحتوى: الديباجة مقابل المواد
    # النمط: يبحث عن أول ظهور لـ **المادة X**
    split_pattern = re.compile(r'(\n\s*\*\*\s*المادة\s*\d+\s*\*\*)', re.MULTILINE)
    parts = split_pattern.split(content, maxsplit=1)

    preamble_content = parts[0].strip()
    articles_block = parts[1] + parts[2] if len(parts) > 2 else ""

    # --- معالجة ملف الـ Parent (المركز السياقي) ---
    parent_filename = f"{doc_slug}.md"
    parent_meta = metadata.copy()
    parent_meta['articles'] = "Fulfull Index"
    parent_meta['summary'] = "الوثيقة الكاملة والنصوص التمهيدية."
    parent_meta['type'] = "وثيقة" # نوع الملف هو وثيقة
    
    parent_content = create_yaml_header(parent_meta) + f"\n# {raw_title}\n\n" + preamble_content
    parent_content += "\n\n## فهرس المواد\n\n*(سيتم تحديث الفهرس لاحقاً بمسارات ملفات ALU)*"
    
    with open(os.path.join(output_dir, parent_filename), 'w', encoding='utf-8') as f:
        f.write(parent_content)
    print(f"✅ تم إنشاء Parent: {parent_filename}")

    # --- معالجة المواد (ALUs) ---
    # نستخدم lookahead لتقسيم الكتل دون حذف عناوين المواد
    article_chunks = re.split(r'(?=\n\s*\*\*\s*المادة\s*\d+\s*\*\*)', articles_block)
    
    previous_id = None
    processed_articles_ids = []
    
    for chunk in article_chunks:
        if not chunk.strip(): continue
        
        # استخراج رقم المادة
        num_match = re.search(r'\*\*\s*المادة\s*(\d+)\s*\*\*', chunk)
        if not num_match: continue
        
        art_num = num_match.group(1)
        art_num_padded = art_num.zfill(3)
        
        alu_id = f"{doc_slug}--مادة-{art_num_padded}"
        alu_filename = f"{alu_id}.md"
        
        # تجهيز الـ YAML
        alu_meta = {
            "id": alu_id,
            "doc": doc_slug,
            "type": "مادة", # نوع الملف هو مادة قانونية
            "domain": metadata.get('domain'),
            "status": metadata.get('status'),
            "articles": art_num,
            "prev": previous_id,
            "next": None, 
            "summary": f"نص المادة {art_num} من النظام.",
            "ocr_corrections": [] 
        }
        
        # حفظ الـ ID الحالي ليصبح 'prev' (السابق) في المادة التالية
        previous_id = alu_id
        processed_articles_ids.append((alu_filename, alu_id))

        # تجميع المحتوى: YAML + عنوان المادة + نص المادة (مع إزالة العنوان المزدوج) + Anchor
        # Note: إزالة التنسيق القديم '**المادة X**' من نص المادة واستبداله بـ '# المادة X'
        article_text_only = chunk.strip().replace(f"**المادة {art_num}**", "", 1).strip()
        full_alu_content = create_yaml_header(alu_meta) + f"# المادة {art_num}\n" + article_text_only + f" {{#art-{art_num}}}"
        
        with open(os.path.join(output_dir, alu_filename), 'w', encoding='utf-8') as f:
            f.write(full_alu_content)
        
    print(f"✅ تم تفتيت {len(processed_articles_ids)} مادة بنجاح للملف: {os.path.basename(file_path)}")

# -----------------------------------------------------
# --- الجزء التشغيلي: اكتشاف الملفات وتشغيلها تلقائياً ---
# -----------------------------------------------------

# 1. تحديد المجلد الحالي
current_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
output_folder = os.path.join(current_dir, "processed_systems_output")

# 2. البحث عن جميع الملفات التي تنتهي بـ '.md' (باستثناء ملف الكود نفسه)
md_files = [f for f in os.listdir(current_dir) if f.endswith('.md') and f != os.path.basename(__file__)]

# 3. التشغيل والتكرار
if not md_files:
    print("❌ لم يتم العثور على أي ملفات .md للمعالجة في هذا المجلد. يرجى وضع ملفات النظام بجانب ملف splitter.py")
else:
    # التأكد من وجود مجلد الإخراج قبل البدء
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        
    print(f"✔️ تم العثور على {len(md_files)} ملف نظام للتقسيم.")
    
    # حلقة (Loop) لمعالجة كل ملف على حدة
    for input_file_name in md_files:
        print("=" * 70)
        print(f"⚙️ بدء معالجة النظام: {input_file_name}")
        input_file_path = os.path.join(current_dir, input_file_name)
        
        try:
            # استدعاء الوظيفة الرئيسية
            process_file_pure_python(input_file_path, output_folder)
        except Exception as e:
            print(f"❌ حدث خطأ غير متوقع أثناء معالجة {input_file_name}. الخطأ: {e}")
            
    print("=" * 70)
    print("✅ اكتملت معالجة جميع الملفات بنجاح. تحقق من المخرجات في مجلد processed_systems_output.")