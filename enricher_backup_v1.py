import os
import re
import yaml
import json
import traceback
from pathlib import Path
from google import genai
from google.genai.errors import APIError
# ملاحظة: تم إزالة استيراد PermissionDeniedError لحل مشكلة ImportError


# --- توابع مساعدة ---

def create_yaml_header(data):
    """إنشاء رأس YAML بتنسيق صحيح"""
    # استخدام allow_unicode=True لضمان ظهور الأحرف العربية بشكل صحيح
    return "---\n" + yaml.dump(data, allow_unicode=True, sort_keys=False) + "---\n"

# *******************************************************************
# دالة الاتصال بـ Gemini API (تم تحديثها لمعالجة الأخطاء الجديدة)
# *******************************************************************

def call_gemini_api(article_text):
    """وظيفة الاتصال الفعلي بـ Gemini API لاستخلاص البيانات الوصفية."""
    
    # 1. إعداد البرومبت (التعليمات للموديل)
    system_prompt = (
        "أنت محلل قانوني خبير في معالجة نصوص القوانين والأنظمة لإنشاء بيانات وصفية (Metadata) دقيقة. "
        "مهمتك هي قراءة نص المادة المرفق وإخراج البيانات المطلوبة في صيغة JSON فقط، دون أي مقدمات أو شرح. "
        "يجب أن تكون عملية النسخ للكلمات الأصلية حرفية لغرض تصحيح الـ OCR. "
        "ركز على استخلاص المعلومات بحد أقصى للحجم (ملخص 30 كلمة، 5-8 كلمات مفتاحية)."
    )
    
    user_prompt = f"""
    بناءً على نص المادة القانونية التالي، أخرج البيانات المطلوبة بصيغة JSON:

    النص:
    ---
    {article_text}
    ---

    البيانات المطلوبة في JSON:
    {{
      "summary": "ملخص مكثف للمادة (30 كلمة كحد أقصى).",
      "keywords": ["كلمة مفتاحية 1", "كلمة مفتاحية 2", "كلمة مفتاحية 3", ...],
      "aspect": "تصنيف المادة هل هي 'إجرائي' (يشرح خطوات/إجراءات) أو 'موضوعي' (يشرح حقوق/واجبات/تعريفات).",
      "ocr_corrections": [
        {{
          "original_word": "الكلمة الأصلية الخاطئة",
          "suggested_correction": "التصحيح المقترح",
          "context": "الجملة المحيطة لتأكيد سياق الخطأ"
        }}
        # أضف كل أخطاء OCR المحتملة (مثل الهمزات، الفواصل، الأخطاء المطبعية الواضحة)
      ]
    }}
    """
    
    print("  ... جارٍ الاتصال بـ Gemini API لمعالجة البيانات...")

    # التحقق من مفتاح API (سيعتمد على متغير البيئة GEMINI_API_KEY)
    if not os.getenv("GEMINI_API_KEY"):
         raise ValueError("يرجى تعيين متغير البيئة GEMINI_API_KEY قبل التشغيل.")

    try:
        # استخدام genai.Client() سيبحث تلقائياً عن المفتاح في متغير البيئة
        client = genai.Client() 
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[user_prompt],
            config={
                "system_instruction": system_prompt, 
                "response_mime_type": "application/json",
                "temperature": 0.0
            }
        )
        
        # تحليل JSON الناتج
        return json.loads(response.text.strip())
        
    except APIError as e:
        # معالجة خطأ الأذونات (Permission Denied) بشكل عام بدلاً من الاستيراد المحدد
        if 'permission denied' in str(e).lower() or '403' in str(e):
            raise APIError("خطأ 403: مفتاح API غير صالح أو غير مسموح به. يرجى التأكد من صلاحية المفتاح.")
        else:
            raise APIError(f"فشل الاتصال بـ Gemini API: {e}")
    except json.JSONDecodeError:
        print(f"تحذير: فشل تحليل JSON من رد الموديل. الرد الخام: {response.text}")
        return {}
    except Exception as e:
        raise Exception(f"حدث خطأ عام أثناء استدعاء API: {e}")

# *******************************************************************
# نهاية الجزء الخاص بالـ API
# *******************************************************************

def load_yaml_and_content(file_path):
    """تحميل رأس YAML ومحتوى النص من ملف Markdown"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # استخدم regex لفصل رأس YAML عن بقية المحتوى
    match = re.search(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    
    if match:
        yaml_header = match.group(1)
        text_content = match.group(2)
        try:
            metadata = yaml.safe_load(yaml_header)
            return metadata, text_content
        except yaml.YAMLError as e:
            print(f"خطأ في تحليل YAML للملف {file_path}: {e}")
            return None, content
    
    return None, content

def update_alu_file(file_path, new_metadata, text_content):
    """تحديث ملف ALU بالبيانات الوصفية الجديدة"""
    
    # 1. تحديث حقول الملخص والتصحيحات
    new_metadata['summary'] = new_metadata.get('summary', 'تم تحديث الملخص بواسطة LLM.')
    new_metadata['keywords'] = new_metadata.get('keywords', [])
    new_metadata['aspect'] = new_metadata.get('aspect', 'غير مصنف')
    new_metadata['ocr_corrections'] = new_metadata.get('ocr_corrections', [])

    # 2. إعادة إنشاء رأس YAML
    updated_yaml_header = create_yaml_header(new_metadata)
    
    # 3. دمج YAML والمحتوى النصي
    final_content = updated_yaml_header + text_content.strip()
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(final_content)

def process_enrichment(input_folder="processed_systems_output"):
    """الوظيفة الرئيسية لتشغيل الإثراء وتصحيح الروابط"""
    
    input_path = Path(input_folder)
    
    if not input_path.exists():
        print(f"❌ لم يتم العثور على مجلد المخرجات: {input_folder}")
        print("يرجى تشغيل splitter.py أولاً لإنشاء المجلد.")
        return

    # 1. المرحلة الأولى: تجميع وترتيب كل ملفات ALU
    doc_alus_map = {} 
    alu_files = sorted(input_path.glob("وثيقة-*.md"))

    for file_path in alu_files:
        if '--مادة-' not in file_path.name:
            continue
            
        metadata, _ = load_yaml_and_content(file_path)
        if not metadata: continue

        doc_slug = metadata.get('doc')
        alu_id = metadata.get('id')
        
        # استخراج رقم المادة للفرز الدقيق
        article_range_match = re.search(r'--مادة-(\d+)', alu_id)
        sort_key = int(article_range_match.group(1)) if article_range_match else 0

        if doc_slug not in doc_alus_map:
            doc_alus_map[doc_slug] = []
        
        doc_alus_map[doc_slug].append({'id': alu_id, 'path': file_path, 'sort_key': sort_key})

    # فرز جميع قوائم الـ ALU حسب الـ Sort Key
    for doc_slug in doc_alus_map:
        doc_alus_map[doc_slug].sort(key=lambda x: x['sort_key'])

    if not doc_alus_map:
        print(f"❌ لم يتم العثور على أي ملفات ALU (التي تحتوي على --مادة-) في مجلد {input_folder}.")
        return

    print(f"تم تجميع {sum(len(v) for v in doc_alus_map.values())} ملف ALU ضمن {len(doc_alus_map)} وثيقة.")
    
    # 2. المرحلة الثانية: تصحيح الروابط والإثراء
    total_processed = 0
    
    for doc_slug, alu_list in doc_alus_map.items():
        print(f"\n--- معالجة الروابط والإثراء للوثيقة: {doc_slug} ({len(alu_list)} ALU) ---")
        
        for i, alu_data in enumerate(alu_list):
            current_path = alu_data['path']
            
            # تحديد السابق والتالي
            prev_id = alu_list[i-1]['id'] if i > 0 else None
            next_id = alu_list[i+1]['id'] if i < len(alu_list) - 1 else None
            
            metadata, text_content = load_yaml_and_content(current_path)
            
            if metadata:
                # تحديث الروابط
                metadata['prev'] = prev_id
                metadata['next'] = next_id
                
                article_text_for_llm = text_content.strip()
                
                try:
                    llm_data = call_gemini_api(article_text_for_llm)
                    
                    # دمج بيانات LLM في الميتاداتا
                    metadata['summary'] = llm_data.get('summary', metadata.get('summary'))
                    metadata['keywords'] = llm_data.get('keywords', metadata.get('keywords', []))
                    metadata['aspect'] = llm_data.get('aspect', metadata.get('aspect', 'غير مصنف'))
                    
                    # تحديث ocr_corrections
                    llm_corrections = llm_data.get('ocr_corrections', [])
                    # تحويل تنسيق القاموس إلى تنسيق YAML: [كلمة: تصحيح]
                    metadata['ocr_corrections'] = {c['original_word']: c['suggested_correction'] for c in llm_corrections if 'original_word' in c and 'suggested_correction' in c}

                    # تحديث الملف بالكامل
                    update_alu_file(current_path, metadata, text_content)
                    print(f"  ✅ تم تحديث وإثراء الملف: {current_path.name}")
                    total_processed += 1
                
                except Exception as e:
                    print(f"  ❌ فشل إثراء الملف {current_path.name}. الخطأ: {e}")
                    # حتى في حالة الفشل، نقوم بتحديث الروابط
                    update_alu_file(current_path, metadata, text_content)
                    total_processed += 1

    print("\n" + "="*70)
    print(f"✅ اكتمل الإثراء. تم تحديث {total_processed} ملف ALU (مع تحديث الروابط).")
    print("==========================================================")

# --- التشغيل المُحسَّن (مع اصطياد الأخطاء) ---
if __name__ == "__main__":
    print("✅ تم تحميل الكود بنجاح. بدء المعالجة...")
    
    try:
        process_enrichment()
    except Exception as e:
        # هذا الجزء سيجبر بايثون على طباعة أي خطأ غير متوقع
        print("\n" + "="*70)
        print("--- خطأ فادح غير متوقع أثناء تشغيل المعالج ---")
        print(f"❌ تعثر السكربت عند هذه النقطة: {e}")
        print("يرجى نسخ الخطأ الكامل الذي سيظهر أدناه وإرساله لي:")
        print("="*70)
        traceback.print_exc()