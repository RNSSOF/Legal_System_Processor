import os
import re
import yaml
import json
import traceback
from pathlib import Path
from collections import defaultdict

# --- 1. التوابع المساعدة الأساسية (Core Utility Functions) ---

def slugify(text):
    """تحويل النص العربي إلى slug صالح لاسم الملف."""
    text = re.sub(r'[\s/\\|:;\'",\.\?]', '_', text)
    text = re.sub(r'[()]', '', text)
    text = re.sub(r'([_])\1+', '_', text)
    return text.strip('_')

def create_yaml_header(data):
    """إنشاء رأس YAML بتنسيق صحيح."""
    return "---\n" + yaml.dump(data, allow_unicode=True, sort_keys=False) + "---\n"

def load_yaml_and_content(file_path):
    """تحميل رأس YAML ومحتوى النص من ملف Markdown."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        match = re.search(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
        
        # إذا لم يكن هناك رأس YAML، نفترض أن المحتوى كله نص
        if not match:
            return {}, content
            
        yaml_header = match.group(1)
        text_content = match.group(2)
        
        try:
            metadata = yaml.safe_load(yaml_header) or {}
            return metadata, text_content
        except yaml.YAMLError:
            return {}, content # إذا فشل تحليل YAML، تجاهله وحافظ على النص
    except Exception as e:
        print(f"تحذير: فشل قراءة الملف {file_path}. الخطأ: {e}")
        return {}, ""

def generate_doc_slug(metadata, filename):
    """إنشاء الـ Slug القياسي (وثيقة-...)."""
    doc_type = metadata.get('النوع', 'وثيقة')
    doc_number = metadata.get('الرقم', '')
    
    # استخدام اسم الملف (بعد التنظيف) كجزء من Slug إذا لم يكن هناك رقم
    if not doc_number or doc_number == '0':
        base_name = filename.replace('.md', '').split('/')[-1]
        slug = f"وثيقة-{slugify(base_name)}"
    else:
        # مثال: قانون-قانون_رقم_13_لسنة_1964
        slug = f"{slugify(doc_type)}-{slugify(filename.replace('.md', ''))}"
    
    return slug

# --- 2. توابع حفظ الملفات (Saving Functions) ---

# تم تعديل جميع توابع الحفظ لقبول 'output_path' الذي يمثل المجلد الفرعي الجديد
def save_log_file(doc_slug, log_entries, output_path):
    """حفظ سجل البناء (build log)."""
    log_file_path = output_path / f"{doc_slug}.build.log"
    with open(log_file_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(log_entries))
    return log_file_path

def save_manifest_file(doc_slug, manifest_data, output_path):
    """حفظ ملف البيان (manifest.json)."""
    manifest_file_path = output_path / f"{doc_slug}.manifest.json"
    with open(manifest_file_path, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, ensure_ascii=False, indent=2)
    return manifest_file_path

def save_parent_file(parent_metadata, parent_content, output_path):
    """حفظ الملف الأم المُعَالَج."""
    doc_slug = parent_metadata.get('doc')
    parent_file_path = output_path / f"{doc_slug}.md"
    
    updated_yaml_header = create_yaml_header(parent_metadata)
    final_content = updated_yaml_header + parent_content.strip()
    
    with open(parent_file_path, 'w', encoding='utf-8') as f:
        f.write(final_content)
    return parent_file_path

def save_alu_file(alu_metadata, alu_text_content, output_path):
    """حفظ الملف الذري (ALU) المنفصل."""
    alu_id = alu_metadata.get('id')
    alu_file_path = output_path / f"{alu_id}.md"
    
    updated_yaml_header = create_yaml_header(alu_metadata)
    final_content = updated_yaml_header + alu_text_content.strip()
    
    with open(alu_file_path, 'w', encoding='utf-8') as f:
        f.write(final_content)
    return alu_file_path

# --- 3. الوظيفة الرئيسية (Main Processing Function) ---

def process_split_file(input_file_path, base_output_folder="processed_systems_output"):
    """
    الوظيفة الرئيسية لقراءة الملف المصدر وتقسيمه إلى وحدات ذرية (ALUs).
    
    هذه الوظيفة تم تعديلها لتنشئ مجلداً فرعياً لكل وثيقة.
    """
    
    log_entries = []
    
    # 1. تحميل المحتوى وتحديد البيانات الوصفية الأولية
    metadata, full_content = load_yaml_and_content(input_file_path)
    filename = input_file_path.name
    log_entries.append(f"1. Initialization: Started processing `{filename}`.")
    
    # إنشاء الـ Slug للوثيقة (يُستخدم كاسم للمجلد الفرعي)
    doc_slug = generate_doc_slug(metadata, filename)
    metadata['doc'] = doc_slug
    log_entries.append(f"2. Doc Slug Generation: Generated slug `{doc_slug}`.")
    
    # =========================================================
    # 💥 التعديل الحاسم لإنشاء المجلد الفرعي الديناميكي 💥
    # =========================================================
    
    # تحديد مسار المجلد الأساسي والفرعي
    base_output_path = Path(base_output_folder)
    doc_output_path = base_output_path / doc_slug 
    
    # إنشاء المجلد الفرعي (parent=True تنشئ المجلدات الرئيسية إذا لم تكن موجودة)
    doc_output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"  --- إنشاء مجلد: {doc_output_path.name}")
    log_entries.append(f"3. Folder Creation: Created dynamic folder `{doc_output_path.name}`.")
    
    # 2. فصل نصوص المواد
    
    # البحث عن قسم "النص الكامل للمواد"
    materials_section_match = re.search(r'(##\s*النص الكامل للمواد.*?)(\Z|##\s*\w+)', full_content, re.DOTALL | re.IGNORECASE)
    
    if not materials_section_match:
        log_entries.append("4. Splitting Failed: 'النص الكامل للمواد' section not found.")
        raise ValueError(f"لم يتم العثور على قسم 'النص الكامل للمواد' في الملف {filename}.")

    materials_text = materials_section_match.group(1)
    
    # إزالة قسم المواد من المحتوى الأصلي (الذي سيصبح الملف الأم)
    parent_content = full_content.replace(materials_text, "## فهرس المواد\n\n[يتم تحديث الفهرس لاحقاً بعد الإثراء]")
    
    # تقسيم نصوص المواد إلى مواد فردية (ALUs)
    alu_splits = re.split(r'\n\s*\*\*المادة\s*(\d+)\s*\*\*\s*\n', materials_text, flags=re.IGNORECASE)
    
    # أول عنصر في alu_splits عادة ما يكون نصًا يسبق أول مادة ويجب تجاهله أو معالجته كديباجة إضافية
    if len(alu_splits) > 1:
        # إزالة النص قبل أول مادة
        alu_splits = alu_splits[1:] 
    else:
        # لم يتم العثور على أي مواد، ربما هو ملف غير مُقسّم جيدًا
        raise ValueError("لم يتم العثور على أرقام مواد صالحة للتقسيم.")
        
    alu_list = []
    
    # تجميع نصوص المواد المنفصلة
    for i in range(0, len(alu_splits), 2):
        article_number = alu_splits[i]
        article_content = alu_splits[i+1].strip()
        alu_list.append((article_number, article_content))

    log_entries.append(f"5. ALU Partitioning: Found {len(alu_list)} articles.")
    
    # 3. حفظ الملفات الذرية والملف الأم

    manifest_data = {'doc': doc_slug, 'parent_file': f"{doc_slug}.md", 'alus': []}
    
    for i, (article_number, article_content) in enumerate(alu_list):
        # تحديد الـ ID والروابط
        alu_id = f"{doc_slug}--مادة-{article_number.zfill(3)}"
        
        # ربط الروابط
        prev_id = f"{doc_slug}--مادة-{alu_list[i-1][0].zfill(3)}" if i > 0 else None
        next_id = f"{doc_slug}--مادة-{alu_list[i+1][0].zfill(3)}" if i < len(alu_list) - 1 else None
        
        # البيانات الوصفية للـ ALU
        alu_metadata = {
            'id': alu_id,
            'doc': doc_slug,
            'type': 'مادة',
            'domain': metadata.get('domain', 'غير مصنف'),
            'status': metadata.get('الحالة', 'قيد التطبيق'),
            'articles': article_number,
            'prev': prev_id,
            'next': next_id,
            # سيتم إضافة 'summary' و 'keywords' و 'ocr_corrections' لاحقاً بواسطة enricher.py
        }
        
        # حفظ ملف ALU
        alu_content = f"# المادة {article_number}\n{article_content} {{#art-{article_number}}}"
        save_alu_file(alu_metadata, alu_content, doc_output_path) # <--- حفظ في المجلد الفرعي
        
        log_entries.append(f"  - Saved ALU: {alu_id}.md")
        manifest_data['alus'].append({'id': alu_id, 'file': f"{alu_id}.md"})

    # تحديث البيانات الوصفية للملف الأم وإضافة فهرس مبسط
    parent_metadata = metadata.copy()
    parent_metadata['articles'] = f"{alu_list[0][0]}-{alu_list[-1][0]}"
    parent_metadata['summary'] = parent_metadata.get('summary', 'النصوص التمهيدية والديباجة.')
    
    # حفظ الملف الأم المُعالج
    save_parent_file(parent_metadata, parent_content, doc_output_path) # <--- حفظ في المجلد الفرعي
    log_entries.append(f"6. Parent File Creation: Saved `{doc_slug}.md` (De-Contented).")
    
    # حفظ ملفات التدقيق
    save_log_file(doc_slug, log_entries, doc_output_path) # <--- حفظ في المجلد الفرعي
    save_manifest_file(doc_slug, [manifest_data], doc_output_path) # <--- حفظ في المجلد الفرعي
    log_entries.append("7. Manifest Generation: Created manifest and log files.")
    
    print(f"  ✅ اكتمل التقسيم بنجاح. تم حفظ {len(alu_list)} مادة في المجلد الفرعي.")
    return True

# --- 4. التشغيل الدفعي (Batch Execution) ---
if __name__ == "__main__":
    source_folder = "source_files" 
    input_path = Path(source_folder)
    
    if not input_path.exists():
        print(f"❌ لم يتم العثور على مجلد الملفات المصدر: {source_folder}")
        print("الرجاء إنشاء مجلد باسم source_files ووضع ملفاتك القانونية بداخله.")
        exit()
        
    # البحث عن جميع ملفات Markdown في مجلد المصدر
    source_files = list(input_path.glob("*.md"))
    
    if not source_files:
        print(f"❌ لم يتم العثور على أي ملفات .md في {source_folder}.")
        exit()
        
    print(f"✅ تم تحميل الكود بنجاح. بدء معالجة {len(source_files)} ملف بشكل دفعي...")
    
    for file_path in source_files:
        print("\n" + "="*70)
        print(f"--- بدء معالجة الملف: {file_path.name} ---")
        try:
            process_split_file(file_path)
        except Exception as e:
            print(f"❌ فشل معالجة {file_path.name}. الخطأ: {e}")
            traceback.print_exc()

    print("\n" + "="*70)
    print("✅ اكتملت معالجة جميع الملفات في الدفعة.")
    print("==========================================================")