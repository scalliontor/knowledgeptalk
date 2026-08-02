#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Áp patch kiểm chứng cho raw_g12_c2.json -> cards_verified/verified_g12_c2.json"""
import json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, 'cards_raw', 'raw_g12_c2.json')
OUT_DIR = os.path.join(BASE, 'cards_verified')
OUT = os.path.join(OUT_DIR, 'verified_g12_c2.json')

d = json.load(open(RAW, encoding='utf-8'))
cards = d['cards']

REJECT = set()          # index thẻ bị loại
FIX = {}                # index -> list mô tả sửa
NEW_CARDS = []          # thẻ trap bổ sung


def note(i, msg):
    FIX.setdefault(i, []).append(msg)


def setf(i, field, val, msg):
    cards[i][field] = val
    note(i, msg)


def repl_fact(i, old_sub, new_text, msg):
    """thay câu fact chứa old_sub bằng new_text"""
    fs = cards[i]['facts']
    for k, f in enumerate(fs):
        if old_sub in f:
            fs[k] = new_text
            note(i, msg)
            return True
    raise SystemExit('KHONG TIM THAY fact %r trong the %d (%s)' % (old_sub, i, cards[i]['name']))


def repl_trap(i, old_sub, new_text, msg):
    ts = cards[i]['traps']
    for k, t in enumerate(ts):
        if old_sub in t:
            ts[k] = new_text
            note(i, msg)
            return True
    raise SystemExit('KHONG TIM THAY trap %r trong the %d' % (old_sub, i))


def add_fact(i, text, msg):
    cards[i]['facts'].append(text)
    note(i, msg)


def add_trap(i, text, msg):
    cards[i]['traps'].append(text)
    note(i, msg)


def add_src(i, url):
    if url not in cards[i]['sources']:
        cards[i]['sources'].append(url)


# ============================================================
# PATCHES
# ============================================================

# ---- [1] Trần Phú: nơi sinh (Phú Yên) vs quê quán (Hà Tĩnh)
repl_fact(1,
          'Trần Phú sinh ngày 1/5/1904, quê ở Đức Thọ, Hà Tĩnh',
          'Trần Phú sinh ngày 1/5/1904 tại thôn An Thổ, huyện Tuy An, tỉnh Phú Yên (nơi cha ông làm quan), '
          'còn quê quán là làng Tùng Ảnh, huyện Đức Thọ, tỉnh Hà Tĩnh; ông hy sinh ngày 6/9/1931 khi mới 27 tuổi.',
          'phân biệt nơi sinh (Tuy An, Phú Yên) với quê quán (Đức Thọ, Hà Tĩnh)')

# ---- [3] Phong trào dân chủ 1936-1939
repl_fact(3,
          'các báo Tin tức, Dân chúng, Lao động được xuất bản bằng tiếng Việt và tiếng Pháp',
          'Từ năm 1937, Đảng xuất bản nhiều tờ báo công khai: bằng tiếng Việt có Tin tức, Dân chúng, Lao động, '
          'Tiến lên; bằng tiếng Pháp có Le Travail (Lao động), Notre Voix (Tiếng nói của chúng ta), En Avant (Tiến lên).',
          'tách rõ báo tiếng Việt (Tin tức, Dân chúng, Lao động) với báo tiếng Pháp (Le Travail, Notre Voix, En Avant)')
setf(3, 'topic_title', 'Phong trào dân chủ 1936 - 1939',
     "topic_title sai (đang là 'Phong trào cách mạng 1930 - 1935')")

# ---- [4] Hội nghị TW 11/1939: địa điểm cụ thể
setf(4, 'place', 'Bà Điểm, Hóc Môn, Gia Định (Nam Kỳ)',
     "place 'Nam Kỳ' -> Bà Điểm, Hóc Môn, Gia Định")
repl_fact(4,
          'Nguyễn Văn Cừ bị Pháp bắt tháng 1/1940',
          'Nguyễn Văn Cừ bị Pháp bắt ngày 18/1/1940 tại Sài Gòn và bị xử bắn ngày 28/8/1941 ở Hóc Môn '
          '(Gia Định) khi mới 29 tuổi.',
          'nêu rõ ngày bị bắt 18/1/1940 và nơi bị xử bắn (Hóc Môn)')

# ---- [16] Tiếp quản Thủ đô: mốc miền Bắc hoàn toàn giải phóng là 16/5/1955 (Cát Bà)
setf(16, 'date_end', '1955-05-16',
     'date_end 13/5/1955 -> 16/5/1955 (mốc miền Bắc hoàn toàn giải phóng)')
repl_fact(16,
          'Ngày 13/5/1955, Hải Phòng',
          'Ngày 13/5/1955, thành phố Hải Phòng được giải phóng; đến ngày 16/5/1955, toán lính Pháp cuối cùng '
          'rút khỏi đảo Cát Bà (Hải Phòng) — đó mới là mốc đánh dấu miền Bắc hoàn toàn giải phóng.',
          'bổ sung mốc 16/5/1955 lính Pháp cuối cùng rút khỏi đảo Cát Bà (SGK), không dừng ở 13/5/1955')
repl_trap(16,
          'lính Pháp cuối cùng rút khỏi Hải Phòng - Cát Bà vào tháng 5/1955',
          'Nhầm miền Bắc sạch bóng quân Pháp ngay ngày 10/10/1954 — Hải Phòng giải phóng 13/5/1955 và toán '
          'lính Pháp cuối cùng rút khỏi đảo Cát Bà ngày 16/5/1955.',
          'trap nêu rõ 13/5 (Hải Phòng) và 16/5/1955 (Cát Bà)')
repl_fact(16,
          'nên miền Bắc được giải phóng dần từ tháng 10/1954 đến tháng 5/1955',
          'Vì Hiệp định Giơ-ne-vơ quy định Pháp phải rút quân theo từng chặng, nên miền Bắc được giải phóng dần '
          'từ ngày 10/10/1954 đến ngày 16/5/1955 chứ không phải cùng một lúc.',
          'chuẩn hoá khoảng thời gian giải phóng miền Bắc')
add_src(16, 'https://www.vietnamplus.vn/buoc-chuyen-dat-nuoc-sau-khi-thuc-dan-phap-rut-khoi-mien-bac-post322146.vnp')

# ---- [17] Cải cách ruộng đất: mô tả đúng tiến trình nhận sai lầm / sửa sai
repl_fact(17,
          'Vì nhận rõ sai lầm, tháng 2/1956 Đảng công bố sai lầm và đình chỉ cải cách',
          'Vì nhận rõ sai lầm, Hội nghị Trung ương lần thứ 9 (tháng 2/1956) đã tuyên bố các sai lầm trong cải '
          'cách ruộng đất, Hội nghị Trung ương lần thứ 10 (tháng 9/1956) quyết định tiến hành sửa sai; công tác '
          'sửa sai làm trong các năm 1956-1957, phục hồi danh dự và tài sản cho phần lớn số người bị quy oan.',
          "sửa mô tả 'tháng 2/1956 đình chỉ cải cách' -> HNTW 9 (2/1956) tuyên bố sai lầm, HNTW 10 (9/1956) quyết định sửa sai")

# ---- [21] Kế hoạch Staley - Taylor: số liệu ấp chiến lược theo SGK
repl_fact(21,
          "đến năm 1962-1963 Mĩ và chính quyền Sài Gòn đã dồn dân lập hơn 9.000 ấp",
          "'Ấp chiến lược' được coi là 'quốc sách' và là xương sống của Chiến tranh đặc biệt: Mĩ và chính quyền "
          "Sài Gòn dự định dồn 10 triệu nông dân vào 16.000 ấp trong tổng số 17.000 ấp toàn miền Nam.",
          'thay số liệu ấp chiến lược không kiểm chứng được bằng số liệu SGK (10 triệu dân / 16.000 trong 17.000 ấp)')
repl_fact(21,
          'Vì nhân dân kiên trì phá ấp, đến đầu năm 1964 có 3.915 trong tổng số 4.248 ấp chiến lược bị phá',
          'Vì nhân dân kiên trì bám đất phá ấp, Mĩ và chính quyền Sài Gòn chỉ lập được khoảng một nửa số ấp dự '
          'định; đến cuối năm 1962, cách mạng kiểm soát trên nửa tổng số ấp với gần 70% nông dân miền Nam, khiến '
          "'quốc sách ấp chiến lược' từng bước phá sản.",
          "thay số liệu '3.915/4.248 ấp' không kiểm chứng được bằng số liệu SGK (kiểm soát trên nửa số ấp, ~70% nông dân cuối 1962)")

# ---- [23] Ấp Bắc: theo SGK là hơn 2.000 binh lính; số liệu thương vong theo vi.wikipedia
repl_fact(23,
          'Quân đội Sài Gòn huy động khoảng 1.400 quân',
          'Theo SGK Lịch sử 12, quân đội Sài Gòn huy động hơn 2.000 binh lính có cố vấn Mĩ chỉ huy, cùng xe bọc '
          'thép M113, máy bay lên thẳng và pháo binh, đánh vào khoảng 350 chiến sĩ quân giải phóng trang bị chủ '
          'yếu vũ khí bộ binh (tài liệu nước ngoài ghi khoảng 1.400 quân Sài Gòn).',
          'quân số quân đội Sài Gòn: theo SGK là hơn 2.000 (thẻ cũ chỉ ghi 1.400 theo tài liệu nước ngoài)')
repl_fact(23,
          'phía Sài Gòn thương vong khoảng 200 người (83 chết)',
          'Kết quả: phía Sài Gòn có 86 người chết và hơn 100 người bị thương, mất 5 máy bay lên thẳng, 3 cố vấn '
          'Mĩ tử trận; quân giải phóng hi sinh 18 người.',
          'số liệu thương vong: 83 chết -> 86 chết, bổ sung số bị thương')
repl_fact(23,
          'Trận Ấp Bắc diễn ra ngày 2/1/1963 tại ấp Bắc, tỉnh Mỹ Tho',
          'Trận Ấp Bắc diễn ra ngày 2/1/1963 tại ấp Bắc, xã Tân Phú, huyện Cai Lậy, tỉnh Mỹ Tho (Định Tường) — '
          'nay thuộc Tiền Giang, cách Sài Gòn khoảng 65 km về phía tây nam.',
          'nêu rõ xã Tân Phú - Cai Lậy, tên tỉnh Định Tường thời đó')

# ---- [24] Vạn Tường: bổ sung kết quả trận đánh theo tài liệu Việt Nam
repl_fact(24,
          'Mĩ huy động khoảng 9.000 quân',
          'Mĩ huy động khoảng 9.000 quân thuộc lính thủy đánh bộ, cùng 105 xe tăng và xe bọc thép, 100 máy bay '
          'lên thẳng, 70 máy bay phản lực và 6 tàu chiến.',
          'bổ sung 6 tàu chiến; bỏ chi tiết phiên hiệu trung đoàn 9 chưa kiểm chứng')
add_fact(24,
         'Theo tài liệu Việt Nam, sau một ngày chiến đấu ta loại khỏi vòng chiến đấu khoảng 900 lính Mĩ, bắn cháy '
         '22 xe tăng và xe bọc thép, hạ 13 máy bay.',
         'bổ sung kết quả trận đánh theo tài liệu Việt Nam')

# ---- [25] Mậu Thân 1968: phạm vi và các đợt theo SGK
repl_fact(25,
          'Quân giải phóng đồng loạt tiến công 6 thành phố lớn và 44 thị xã',
          'Quân dân miền Nam đồng loạt tiến công và nổi dậy ở 37 trong số 44 tỉnh, 4 trong 6 đô thị lớn và 64 '
          'trong 242 quận lị, đánh cả vào các cơ quan đầu não của Mĩ và chính quyền Sài Gòn ở Sài Gòn, Huế.',
          "phạm vi tiến công sai ('6 thành phố lớn và 44 thị xã') -> 37/44 tỉnh, 4/6 đô thị lớn, 64/242 quận lị (SGK)")
repl_fact(25,
          'Đợt 1 kéo dài từ 30/1 đến 28/3/1968',
          'Cuộc Tổng tiến công và nổi dậy diễn ra qua ba đợt: đợt 1 từ đêm 30/1 đến ngày 25/2/1968, đợt 2 trong '
          'tháng 5 và 6/1968, đợt 3 trong tháng 8 và 9/1968.',
          'các đợt Mậu Thân theo SGK (đợt 1 kết thúc 25/2, không phải 28/3)')

# ---- [19] Mặt trận DTGP miền Nam: làm rõ mốc bầu Chủ tịch chính thức
repl_fact(19,
          'Luật sư Nguyễn Hữu Thọ được cử làm Chủ tịch Mặt trận.',
          'Luật sư Nguyễn Hữu Thọ được cử làm Chủ tịch Ủy ban Trung ương lâm thời của Mặt trận, và được chính '
          'thức bầu làm Chủ tịch tại Đại hội lần thứ nhất của Mặt trận (tháng 2/1962, Tây Ninh).',
          'làm rõ: 20/12/1960 cử làm Chủ tịch lâm thời, chính thức bầu tại Đại hội I của Mặt trận (2/1962)')

# ---- [22] Chiến tranh đặc biệt: thay số liệu vùng kiểm soát chung chung bằng mốc SGK
repl_fact(22,
          'đến năm 1964 lực lượng cách mạng đã kiểm soát 50-90% địa bàn nhiều tỉnh lớn',
          'Vì quân dân miền Nam đánh bại các cuộc càn quét và phá từng mảng "ấp chiến lược", chiến thắng Bình Giã '
          '(2/12/1964) đã làm phá sản về cơ bản chiến lược Chiến tranh đặc biệt.',
          "thay số liệu '50-90% địa bàn' không kiểm chứng được bằng mốc SGK: chiến thắng Bình Giã 2/12/1964")
repl_fact(22,
          'Chiến tranh đặc biệt phá sản hoàn toàn khi lính thủy đánh bộ Mĩ đổ bộ vào Đà Nẵng ngày 8/3/1965',
          'Các chiến thắng An Lão, Ba Gia, Đồng Xoài trong nửa đầu năm 1965 làm Chiến tranh đặc biệt phá sản hoàn '
          'toàn; ngày 8/3/1965 lính thủy đánh bộ Mĩ đổ bộ vào Đà Nẵng, mở đầu việc Mĩ trực tiếp đưa quân viễn '
          'chinh vào tham chiến.',
          "làm rõ chiều nhân - quả: CTĐB phá sản hoàn toàn giữa 1965 (An Lão, Ba Gia, Đồng Xoài); 8/3/1965 là mốc Mĩ đưa quân viễn chinh")

# ---- [26],[27] topic_title lệch bài (đang gán vào chủ đề 1965-1968)
TOPIC_6973 = ('Chiến đấu chống chiến lược "Việt Nam hóa chiến tranh" và "Đông Dương hóa chiến tranh" '
              'của đế quốc Mĩ (1969 - 1973)')
setf(26, 'topic_title', TOPIC_6973,
     'topic_title sai (đang là chủ đề "Chiến tranh cục bộ" 1965-1968)')
setf(27, 'topic_title', TOPIC_6973,
     'topic_title sai (sự kiện 12/1972 bị gán vào chủ đề "Chiến tranh cục bộ" 1965-1968)')

# ---- [41] Đại sứ quán: mốc 5/8/1995 là khai trương ĐSQ Hoa Kỳ tại Hà Nội
repl_fact(41,
          'Đại sứ quán Việt Nam tại Washington mở cửa ngày 5/8/1995',
          'Ngày 5/8/1995, Ngoại trưởng Mĩ Warren Christopher tới Hà Nội, cùng Bộ trưởng Ngoại giao Nguyễn Mạnh Cầm '
          'ký nghị định thư thiết lập quan hệ ngoại giao và khai trương Đại sứ quán Hoa Kỳ tại Hà Nội; hai nước '
          'trao đổi đại sứ đầu tiên vào tháng 5/1997.',
          'sửa mốc đại sứ quán: 5/8/1995 là ngày khai trương ĐSQ Hoa Kỳ tại Hà Nội (thẻ cũ ghi nhầm là ĐSQ Việt Nam tại Washington)')
add_src(41, 'https://cand.vn/Su-kien-Binh-luan-thoi-su/Mot-so-cot-moc-dang-nho-trong-25-nam-binh-thuong-hoa-quan-he-Viet-Nam-Hoa-Ky-i572383/')

# ---- [47] Hiệp định Paris: bổ sung mốc hội nghị bốn bên
add_fact(47,
         'Lúc đầu (từ 13/5/1968) đàm phán chỉ có hai bên là Việt Nam Dân chủ Cộng hòa và Hoa Kỳ; từ ngày 25/1/1969 '
         'hội nghị mở rộng thành bốn bên, có thêm Mặt trận Dân tộc Giải phóng miền Nam Việt Nam (sau là Chính phủ '
         'Cách mạng lâm thời) và Việt Nam Cộng hòa.',
         'bổ sung mốc chuyển từ đàm phán hai bên (13/5/1968) sang hội nghị bốn bên (25/1/1969)')

# ============================================================
# THẺ BẪY BỔ SUNG (lấp đúng khoảng trống bài 21-23 của chunk này)
# ============================================================
TOPIC_21 = 'Những năm đầu của cuộc kháng chiến toàn quốc chống thực dân Pháp (1946 - 1950)'
TOPIC_22 = 'Bước phát triển của cuộc kháng chiến toàn quốc chống thực dân Pháp (1951 - 1953)'
TOPIC_23 = 'Cuộc kháng chiến toàn quốc chống thực dân Pháp kết thúc (1953 - 1954)'

NEW_CARDS.extend([
 {
  "name": "Chiến dịch Việt Bắc thu - đông 1947",
  "kind": "event",
  "year": 1947,
  "date_start": "1947-10-07",
  "date_end": "1947-12-19",
  "place": "Căn cứ địa Việt Bắc (Bắc Kạn, Thái Nguyên, Tuyên Quang, Cao Bằng)",
  "actors": ["Quân đội và dân quân Việt Bắc", "thực dân Pháp", "Hồ Chí Minh", "Võ Nguyên Giáp"],
  "summary": "Cuộc tiến công lên Việt Bắc thu - đông 1947 của Pháp bị đánh bại, buộc Pháp phải bỏ 'đánh nhanh thắng nhanh' để chuyển sang 'đánh lâu dài'.",
  "facts": [
   "Ngày 7/10/1947, thực dân Pháp huy động khoảng 12.000 quân tinh nhuệ cùng hầu hết máy bay ở Đông Dương, chia làm ba cánh (nhảy dù, bộ binh, thủy binh) tiến công lên căn cứ địa Việt Bắc.",
   "Mục tiêu của Pháp là tiêu diệt cơ quan đầu não kháng chiến, tiêu diệt bộ đội chủ lực, phá tan căn cứ địa Việt Bắc và khóa chặt biên giới Việt - Trung, nhằm nhanh chóng kết thúc chiến tranh.",
   "Quân dân ta chủ động bao vây, chia cắt và phục kích trên các hướng: ở Bắc Kạn - Chợ Mới, trên sông Lô (Đoan Hùng, Khe Lau) và trên đường số 4 (Bản Sao - đèo Bông Lau).",
   "Ngày 19/12/1947, đại bộ phận quân Pháp phải rút khỏi Việt Bắc; ta loại khỏi vòng chiến đấu hơn 6.000 tên địch, bắn rơi 16 máy bay, bắn chìm 11 tàu chiến và ca nô.",
   "Vì cuộc tiến công lên Việt Bắc thất bại, thực dân Pháp buộc phải CHUYỂN TỪ chiến lược 'đánh nhanh thắng nhanh' SANG 'đánh lâu dài', thực hiện âm mưu 'dùng người Việt đánh người Việt, lấy chiến tranh nuôi chiến tranh'.",
   "Cơ quan đầu não kháng chiến được bảo toàn, bộ đội chủ lực ta trưởng thành; ngày 11/6/1948, tại chiến khu Việt Bắc, Chủ tịch Hồ Chí Minh ra Lời kêu gọi thi đua ái quốc để đẩy mạnh kháng chiến toàn dân, toàn diện."
  ],
  "traps": [
   "ĐẢO NGƯỢC CHIỀU NHÂN - QUẢ: sau thất bại Việt Bắc 1947, Pháp chuyển TỪ 'đánh nhanh thắng nhanh' SANG 'đánh lâu dài' — nói ngược lại (từ đánh lâu dài sang đánh nhanh thắng nhanh) là SAI.",
   "Tháng 6/1948, Chủ tịch Hồ Chí Minh KHÔNG đi công du nước ngoài — ngày 11/6/1948 Người ra Lời kêu gọi thi đua ái quốc tại chiến khu Việt Bắc.",
   "Nhầm Việt Bắc thu - đông 1947 là chiến dịch do ta chủ động mở — đây là cuộc tiến công của Pháp, ta phản công đánh bại; chiến dịch đầu tiên ta chủ động mở là Biên giới thu - đông 1950."
  ],
  "aliases": ["Việt Bắc thu đông 1947", "chiến dịch Việt Bắc 1947", "chiến thắng Việt Bắc thu - đông 1947", "Pháp tiến công Việt Bắc 1947"],
  "topic_title": TOPIC_21,
  "lessons": [{"book": "NXBDG", "bai": 21}],
  "sources": [
   "https://vi.wikipedia.org/wiki/Chi%E1%BA%BFn_d%E1%BB%8Bch_Vi%E1%BB%87t_B%E1%BA%AFc",
   "https://special.nhandan.vn/chien-dich-viet-bac-thu-dong/index.html",
   "https://nvsk.vnanet.vn/chien-thang-viet-bac-thu-dong-nam-1947-gia-tri-lich-su-va-hien-thuc-1-40021.vna"
  ],
  "fixed": ["thẻ bổ sung: phủ bẫy chiều nhân - quả 'đánh nhanh thắng nhanh -> đánh lâu dài' và bẫy 6/1948"]
 },
 {
  "name": "Kế hoạch Đờ Lát đơ Tát-xi-nhi (12/1950)",
  "kind": "event",
  "year": 1950,
  "date_start": "1950-12",
  "date_end": "1951",
  "place": "Bắc Bộ (Việt Nam)",
  "actors": ["Đờ Lát đơ Tát-xi-nhi", "thực dân Pháp", "đế quốc Mĩ"],
  "summary": "Kế hoạch quân sự tháng 12/1950 của Pháp có Mĩ giúp sức, nhằm tìm cách giành lại quyền chủ động chiến lược đã mất sau thất bại Biên giới thu - đông 1950.",
  "facts": [
   "Ngày 6/12/1950, Chính phủ Pháp cử Đại tướng Đờ Lát đơ Tát-xi-nhi (De Lattre de Tassigny) làm Tổng chỉ huy quân đội viễn chinh kiêm Cao ủy Pháp ở Đông Dương; tháng 12/1950 ông đề ra một kế hoạch quân sự mới.",
   "Vì thất bại trong chiến dịch Biên giới thu - đông 1950, Pháp ĐÃ MẤT quyền chủ động chiến lược trên chiến trường chính Bắc Bộ; kế hoạch Đờ Lát đơ Tát-xi-nhi ra đời nhằm TÌM CÁCH GIÀNH LẠI quyền chủ động đã mất đó.",
   "Kế hoạch gồm bốn điểm: gấp rút tập trung quân Âu - Phi xây dựng lực lượng cơ động mạnh và ra sức phát triển ngụy quân; xây dựng phòng tuyến công sự xi măng cốt sắt ('boong ke') lập 'vành đai trắng' bao quanh trung du và đồng bằng Bắc Bộ.",
   "Hai điểm còn lại là tiến hành 'chiến tranh tổng lực', bình định vùng tạm chiếm, vơ vét sức người sức của; và đánh phá hậu phương ta bằng biệt kích, thổ phỉ, chiến tranh tâm lý và chiến tranh kinh tế.",
   "Kế hoạch được xây dựng trên cơ sở viện trợ ngày càng tăng của Mĩ, đánh dấu sự dính líu và can thiệp sâu hơn của Mĩ vào chiến tranh Đông Dương.",
   "Kế hoạch đẩy cuộc kháng chiến của ta, nhất là ở vùng sau lưng địch, vào thời kỳ khó khăn, nhưng cuối cùng bị phá sản trước các cuộc tiến công của ta trong những năm 1951 - 1953."
  ],
  "traps": [
   "Nói kế hoạch Đờ Lát đơ Tát-xi-nhi ra đời khi Pháp 'đang ở thế chủ động' là SAI — sau Biên giới thu - đông 1950 Pháp đã MẤT quyền chủ động chiến lược, kế hoạch nhằm TÌM CÁCH GIÀNH LẠI quyền chủ động đã mất.",
   "Nhầm kế hoạch Đờ Lát đơ Tát-xi-nhi (12/1950) với kế hoạch Rơ-ve (1949) hay kế hoạch Nava (1953).",
   "Nhầm kế hoạch này do Mĩ trực tiếp vạch ra — đây là kế hoạch của Pháp, dựa trên viện trợ và sự can thiệp ngày càng sâu của Mĩ."
  ],
  "aliases": ["kế hoạch Đờ Lát đơ Tát-xi-nhi", "kế hoạch Đờ Lát đờ Tátxinhi 1950", "De Lattre de Tassigny", "kế hoạch quân sự tháng 12/1950 của Pháp"],
  "topic_title": TOPIC_22,
  "lessons": [{"book": "NXBDG", "bai": 22}],
  "sources": [
   "https://vi.wikipedia.org/wiki/Jean_de_Lattre_de_Tassigny",
   "https://nguoikesu.com/tu-lieu/quan-su/chien-dich-hoang-hoa-tham-nam-1950-1951"
  ],
  "fixed": ["thẻ bổ sung: phủ bẫy 'Pháp đang chủ động' vs 'tìm cách giành lại quyền chủ động đã mất'"]
 },
 {
  "name": "Đại hội đại biểu lần thứ II của Đảng (2/1951)",
  "kind": "event",
  "year": 1951,
  "date_start": "1951-02-11",
  "date_end": "1951-02-19",
  "place": "xã Vinh Quang, huyện Chiêm Hóa, tỉnh Tuyên Quang",
  "actors": ["Hồ Chí Minh", "Trường Chinh", "Đảng Lao động Việt Nam"],
  "summary": "Đại hội kháng chiến thắng lợi họp tháng 2/1951 ở Tuyên Quang: Đảng ra hoạt động công khai với tên Đảng Lao động Việt Nam, Trường Chinh làm Tổng Bí thư.",
  "facts": [
   "Đại hội đại biểu lần thứ II của Đảng họp từ ngày 11 đến ngày 19/2/1951 tại xã Vinh Quang, huyện Chiêm Hóa, tỉnh Tuyên Quang.",
   "Dự đại hội có 158 đại biểu chính thức và 53 đại biểu dự khuyết, thay mặt cho hơn 76 vạn đảng viên (766.349 đảng viên).",
   "Đại hội quyết định tách Đảng Cộng sản Đông Dương để thành lập ở mỗi nước Đông Dương một đảng riêng; ở Việt Nam, Đảng ra hoạt động công khai với tên mới là Đảng Lao động Việt Nam.",
   "TRƯỜNG CHINH được bầu lại làm Tổng Bí thư Ban Chấp hành Trung ương Đảng, còn HỒ CHÍ MINH được bầu làm Chủ tịch Đảng — hai chức danh khác nhau.",
   "Đại hội thông qua Báo cáo chính trị của Hồ Chí Minh và Báo cáo 'Bàn về cách mạng Việt Nam' của Trường Chinh; quyết định xuất bản báo Nhân dân làm cơ quan ngôn luận của Trung ương Đảng.",
   "Ngay sau Đại hội, ngày 3/3/1951, Mặt trận Việt Minh và Hội Liên Việt hợp nhất thành Mặt trận Liên hiệp quốc dân Việt Nam (Mặt trận Liên Việt); Đại hội II được gọi là 'Đại hội kháng chiến thắng lợi'."
  ],
  "traps": [
   "'Tổng Bí thư được bầu tại Đại hội II (2/1951) là Hồ Chí Minh' là SAI — Tổng Bí thư là TRƯỜNG CHINH, còn Hồ Chí Minh giữ chức Chủ tịch Đảng.",
   "Nhầm Đại hội II đổi tên Đảng thành Đảng Cộng sản Việt Nam — năm 1951 Đảng lấy tên Đảng Lao động Việt Nam; tên Đảng Cộng sản Việt Nam có từ Đại hội IV (12/1976).",
   "Nhầm Đại hội II họp ở Hà Nội hay ở nước ngoài — đại hội họp tại xã Vinh Quang, Chiêm Hóa, Tuyên Quang (căn cứ địa Việt Bắc)."
  ],
  "aliases": ["Đại hội II của Đảng", "Đại hội đại biểu toàn quốc lần thứ II", "Đại hội Đảng tháng 2/1951", "Đại hội kháng chiến thắng lợi"],
  "topic_title": TOPIC_22,
  "lessons": [{"book": "NXBDG", "bai": 22}],
  "sources": ["https://vi.wikipedia.org/wiki/%C4%90%E1%BA%A1i_h%E1%BB%99i_%C4%90%E1%BA%A3ng_C%E1%BB%99ng_s%E1%BA%A3n_Vi%E1%BB%87t_Nam_II"],
  "fixed": ["thẻ bổ sung: phủ bẫy 'Đại hội II bầu ai làm Tổng Bí thư' (Trường Chinh, không phải Hồ Chí Minh)"]
 },
 {
  "name": "Ba chiến dịch tiến công cuối năm 1950 - giữa năm 1951 (Trần Hưng Đạo, Hoàng Hoa Thám, Quang Trung)",
  "kind": "event",
  "year": 1951,
  "date_start": "1950-12",
  "date_end": "1951-06",
  "place": "trung du và đồng bằng Bắc Bộ",
  "actors": ["Quân đội nhân dân Việt Nam", "Võ Nguyên Giáp", "quân Pháp"],
  "summary": "Từ cuối năm 1950 đến giữa năm 1951, ta mở BA chiến dịch tiến công lớn ở trung du và đồng bằng Bắc Bộ nhằm giữ vững quyền chủ động chiến lược.",
  "facts": [
   "Sau chiến thắng Biên giới thu - đông 1950, để giữ vững quyền chủ động, từ cuối năm 1950 đến giữa năm 1951 ta liên tiếp mở BA chiến dịch tiến công quy mô lớn.",
   "Chiến dịch Trần Hưng Đạo (còn gọi là chiến dịch Trung du) đánh ở vùng trung du Bắc Bộ từ cuối tháng 12/1950 đến tháng 1/1951.",
   "Chiến dịch Hoàng Hoa Thám (chiến dịch Đường số 18) đánh trên tuyến đường 18 vùng Đông Bắc, từ tháng 3 đến tháng 4/1951.",
   "Chiến dịch Quang Trung (chiến dịch Hà - Nam - Ninh) đánh ở vùng Hà Nam, Nam Định, Ninh Bình từ tháng 5 đến tháng 6/1951.",
   "Vì cả ba chiến dịch đều đánh vào vùng trung du và đồng bằng — nơi địch có hệ thống phòng ngự mạnh và phát huy được ưu thế binh khí kĩ thuật — nên ta tiêu diệt được nhiều sinh lực địch nhưng không đạt kết quả như dự định.",
   "Rút kinh nghiệm, từ cuối năm 1951 ta chuyển hướng tiến công lên vùng rừng núi, nơi địch yếu và sở trường của ta được phát huy, mở các chiến dịch Hòa Bình, Tây Bắc, Thượng Lào."
  ],
  "traps": [
   "Nhầm số chiến dịch: từ cuối năm 1950 đến giữa năm 1951 ta mở BA chiến dịch (Trần Hưng Đạo, Hoàng Hoa Thám, Quang Trung), không phải hai hay bốn.",
   "Nhầm ba chiến dịch này đánh ở rừng núi — chúng đánh ở trung du và đồng bằng Bắc Bộ, nơi địch mạnh, nên không đạt kết quả như mong muốn.",
   "Nhầm tên chiến dịch với địa bàn: Trần Hưng Đạo = trung du; Hoàng Hoa Thám = đường số 18; Quang Trung = Hà - Nam - Ninh."
  ],
  "aliases": ["chiến dịch Trần Hưng Đạo", "chiến dịch Hoàng Hoa Thám", "chiến dịch Quang Trung", "chiến dịch Trung du 1951", "chiến dịch Đường 18", "chiến dịch Hà - Nam - Ninh"],
  "topic_title": TOPIC_22,
  "lessons": [{"book": "NXBDG", "bai": 22}],
  "sources": [
   "https://vi.wikipedia.org/wiki/Chi%E1%BA%BFn_d%E1%BB%8Bch_Ho%C3%A0ng_Hoa_Th%C3%A1m",
   "https://nguoikesu.com/tu-lieu/quan-su/chien-dich-hoang-hoa-tham-nam-1950-1951"
  ],
  "fixed": ["thẻ bổ sung: phủ bẫy 'cuối 1950 - giữa 1951 ta mở mấy chiến dịch' (đáp án: 3)"]
 },
 {
  "name": "Chiến dịch Hòa Bình, Tây Bắc và Thượng Lào (1951 - 1953)",
  "kind": "event",
  "year": 1952,
  "date_start": "1951-12-10",
  "date_end": "1953-05-18",
  "place": "Hòa Bình, Tây Bắc Việt Nam và Thượng Lào",
  "actors": ["Quân đội nhân dân Việt Nam", "quân Pháp", "bộ đội Pathét Lào"],
  "summary": "Ba chiến dịch tiến công lên rừng núi trong các năm 1951-1953, giữ vững quyền chủ động và chuẩn bị cho Đông - Xuân 1953-1954.",
  "facts": [
   "Chiến dịch Hòa Bình diễn ra từ ngày 10/12/1951 đến ngày 25/2/1952, sau khi Pháp đánh chiếm Hòa Bình (tháng 11/1951) để nối lại 'hành lang Đông - Tây'.",
   "Kết thúc chiến dịch, TA loại khỏi vòng chiến đấu hơn 6.000 tên địch và GIẢI PHÓNG khu vực Hòa Bình - sông Đà; quân Pháp phải rút khỏi thị xã Hòa Bình ngày 23/2/1952 — tức là sau chiến dịch, lòng chảo Hòa Bình thuộc về ta chứ không phải Pháp.",
   "Chiến dịch Tây Bắc thu - đông 1952 diễn ra từ ngày 14/10 đến ngày 10/12/1952; ta giải phóng Nghĩa Lộ, phần lớn Sơn La (trừ cứ điểm Nà Sản), Yên Bái và Lai Châu.",
   "Vì địch vẫn giữ được tập đoàn cứ điểm Nà Sản, chiến dịch Tây Bắc 1952 mới chỉ làm phá sản MỘT PHẦN âm mưu lập 'xứ Thái tự trị' của Pháp, chứ chưa xóa bỏ hoàn toàn.",
   "Chiến dịch Thượng Lào diễn ra từ ngày 8/4 đến ngày 18/5/1953, do liên quân Việt - Lào phối hợp mở.",
   "Kết quả chiến dịch Thượng Lào: giải phóng tỉnh Sầm Nưa, một phần tỉnh Xiêng Khoảng và tỉnh Phongxalì, với hơn 4.000 km² và trên 30 vạn dân, mở rộng căn cứ kháng chiến của cách mạng Lào."
  ],
  "traps": [
   "Nhầm sau chiến dịch Hòa Bình đông - xuân 1951-1952 thì Pháp chiếm giữ lòng chảo Hòa Bình — thực tế TA giải phóng khu vực Hòa Bình - sông Đà, quân Pháp phải rút chạy.",
   "Nhầm chiến dịch Tây Bắc thu - đông 1952 đã phá sản HOÀN TOÀN âm mưu lập 'xứ Thái tự trị' — mới chỉ phá sản MỘT PHẦN vì địch còn giữ Nà Sản.",
   "Nhầm thời gian chiến dịch Thượng Lào — chiến dịch diễn ra từ 8/4 đến 18/5/1953, do liên quân Việt - Lào tiến hành, không phải năm 1954."
  ],
  "aliases": ["chiến dịch Hòa Bình 1951-1952", "chiến dịch Tây Bắc thu - đông 1952", "chiến dịch Thượng Lào 1953", "xứ Thái tự trị", "giải phóng Sầm Nưa"],
  "topic_title": TOPIC_22,
  "lessons": [{"book": "NXBDG", "bai": 22}],
  "sources": [
   "https://vi.wikipedia.org/wiki/Chi%E1%BA%BFn_d%E1%BB%8Bch_H%C3%B2a_B%C3%ACnh",
   "https://nvsk.vnanet.vn/chien-dich-hoa-binh-10-12-1951-25-2-1952-1-34067.vna",
   "https://vi.wikipedia.org/wiki/Chi%E1%BA%BFn_d%E1%BB%8Bch_Th%C6%B0%E1%BB%A3ng_L%C3%A0o"
  ],
  "fixed": ["thẻ bổ sung: phủ bẫy Hòa Bình (TA chiếm lòng chảo), Tây Bắc 1952 (phá sản MỘT PHẦN 'xứ Thái tự trị'), Thượng Lào 8/4-18/5/1953"]
 },
 {
  "name": "Kế hoạch Nava (7/1953) và cuộc tiến công chiến lược Đông - Xuân 1953 - 1954",
  "kind": "event",
  "year": 1953,
  "date_start": "1953-07",
  "date_end": "1954-02",
  "place": "Đông Dương",
  "actors": ["Hăng-ri Nava", "thực dân Pháp", "đế quốc Mĩ", "liên quân Việt - Lào"],
  "summary": "Kế hoạch Nava gồm HAI bước nhằm kết thúc chiến tranh trong 18 tháng, bị ta làm phá sản bước đầu bằng các đòn tiến công Đông - Xuân 1953-1954.",
  "facts": [
   "Ngày 7/5/1953, được Mĩ thỏa thuận, Chính phủ Pháp cử tướng Hăng-ri Nava (Henri Navarre) làm Tổng chỉ huy quân đội viễn chinh Pháp ở Đông Dương; tháng 7/1953 Nava đề ra kế hoạch quân sự mang tên ông, hi vọng trong 18 tháng sẽ 'kết thúc chiến tranh trong danh dự'.",
   "Kế hoạch Nava gồm HAI BƯỚC (không phải ba): bước thứ nhất trong thu - đông 1953 và xuân 1954, giữ thế phòng ngự chiến lược ở Bắc Bộ đồng thời tiến công chiến lược ở Trung Bộ và Nam Đông Dương; bước thứ hai từ thu - đông 1954, chuyển lực lượng ra chiến trường Bắc Bộ, thực hiện tiến công chiến lược, giành thắng lợi quyết định để kết thúc chiến tranh.",
   "Tháng 12/1953, ta tiến công thị xã Lai Châu, giải phóng toàn tỉnh Lai Châu (trừ Điện Biên Phủ), buộc Nava phải điều quân tăng cường cho Điện Biên Phủ.",
   "Cũng trong tháng 12/1953, liên quân Việt - Lào tiến công TRUNG LÀO (không phải Thượng Lào), giải phóng thị xã Thà Khẹt và uy hiếp Xênô, buộc Nava tăng quân cho Xênô.",
   "Cuối tháng 1/1954, liên quân Việt - Lào tiến công Thượng Lào, giải phóng lưu vực sông Nậm Hu và tỉnh Phongxalì, buộc Nava tăng quân cho Luông Phabang và Mường Sài.",
   "Đầu tháng 2/1954, ta tiến công BẮC TÂY NGUYÊN (không phải Tây Bắc), giải phóng thị xã Kon Tum và uy hiếp Plâyku, buộc Nava tăng quân cho Plâyku.",
   "Vì bị ta tiến công ở nhiều hướng, Nava buộc phải phân tán khối quân cơ động chiến lược ra các nơi tập trung quân, làm kế hoạch tập trung 'quả đấm thép' bước đầu phá sản."
  ],
  "traps": [
   "Kế hoạch Nava gồm HAI bước — trả lời 'ba bước' là SAI.",
   "Tháng 12/1953, liên quân Việt - Lào tiến công TRUNG LÀO (giải phóng Thà Khẹt, uy hiếp Xênô), KHÔNG phải Thượng Lào; hướng Thượng Lào là cuối tháng 1/1954.",
   "Đầu tháng 2/1954, ta tiến công BẮC TÂY NGUYÊN (giải phóng Kon Tum), KHÔNG phải Tây Bắc; hướng Tây Bắc (Lai Châu) là tháng 12/1953."
  ],
  "aliases": ["kế hoạch Nava", "kế hoạch Navarre 1953", "Đông - Xuân 1953-1954", "cuộc tiến công chiến lược Đông Xuân 1953-1954"],
  "topic_title": TOPIC_23,
  "lessons": [{"book": "NXBDG", "bai": 23}],
  "sources": [
   "https://vi.wikipedia.org/wiki/K%E1%BA%BF_ho%E1%BA%A1ch_Navarre",
   "https://vi.wikipedia.org/wiki/Chi%E1%BA%BFn_c%E1%BB%A5c_%C4%90%C3%B4ng_Xu%C3%A2n_1953%E2%80%931954"
  ],
  "fixed": ["thẻ bổ sung: phủ bẫy 'Nava 2 bước', 'tháng 12/1953 tiến công Trung Lào', 'đầu 2/1954 tiến công Bắc Tây Nguyên'"]
 },
 {
  "name": "Chiến dịch Điện Biên Phủ (13/3 - 7/5/1954)",
  "kind": "event",
  "year": 1954,
  "date_start": "1954-03-13",
  "date_end": "1954-05-07",
  "place": "thung lũng Mường Thanh, Điện Biên Phủ (Lai Châu cũ, nay là tỉnh Điện Biên)",
  "actors": ["Võ Nguyên Giáp", "Quân đội nhân dân Việt Nam", "tướng Đờ Cát-xtơ-ri", "quân Pháp"],
  "summary": "Chiến dịch quyết chiến chiến lược năm 1954 tiêu diệt tập đoàn cứ điểm Điện Biên Phủ, đập tan kế hoạch Nava và dẫn tới Hiệp định Giơ-ne-vơ.",
  "facts": [
   "Chiến dịch Điện Biên Phủ diễn ra từ ngày 13/3 đến ngày 7/5/1954 (56 ngày đêm) tại thung lũng Mường Thanh, do Đại tướng Võ Nguyên Giáp làm Tư lệnh kiêm Bí thư Đảng ủy mặt trận.",
   "Điện Biên Phủ được Pháp - Mĩ xây dựng thành tập đoàn cứ điểm mạnh nhất Đông Dương với 49 cứ điểm chia thành ba phân khu, khoảng 16.200 quân, được coi là 'pháo đài bất khả xâm phạm'.",
   "Vì thấy địch tăng cường phòng ngự, Bộ chỉ huy chiến dịch đã thay đổi phương châm từ 'đánh nhanh, thắng nhanh' SANG 'đánh chắc, tiến chắc' — chính quyết định thay đổi này góp phần quyết định thắng lợi.",
   "Chiến dịch diễn ra qua ba đợt: đợt 1 (13 - 17/3/1954) tiêu diệt Him Lam và toàn bộ phân khu Bắc; đợt 2 (30/3 - 26/4/1954) đánh các cao điểm phía đông như A1, C1, D1, E1 và vây lấn sân bay Mường Thanh; đợt 3 (1 - 7/5/1954) tổng công kích tiêu diệt toàn bộ tập đoàn cứ điểm.",
   "17 giờ 30 phút ngày 7/5/1954, lá cờ 'Quyết chiến quyết thắng' tung bay trên nóc hầm chỉ huy; ta bắt sống tướng Đờ Cát-xtơ-ri cùng toàn bộ Bộ chỉ huy, loại khỏi vòng chiến đấu 16.200 địch, phá hủy và bắn rơi 62 máy bay.",
   "Vì Điện Biên Phủ thất thủ, kế hoạch Nava bị đập tan hoàn toàn và Pháp buộc phải ký Hiệp định Giơ-ne-vơ ngày 21/7/1954 — thắng lợi quân sự đã quyết định thắng lợi trên bàn đàm phán, chứ không phải ngược lại."
  ],
  "traps": [
   "PHÂN BIỆT: Chiến dịch Điện Biên Phủ diễn ra 13/3 - 7/5/1954 ở Điện Biên, chống thực dân Pháp; còn 'Điện Biên Phủ trên không' là trận chống tập kích bằng B-52 của Mĩ ở Hà Nội - Hải Phòng, 18 - 29/12/1972. Hai sự kiện khác nhau, cách nhau 18 năm.",
   "Nhầm phương châm chiến dịch: ta đổi TỪ 'đánh nhanh, thắng nhanh' SANG 'đánh chắc, tiến chắc' — nói ngược lại là SAI.",
   "Nhầm chiều nhân - quả: chiến thắng Điện Biên Phủ (7/5/1954) diễn ra TRƯỚC và tạo điều kiện cho việc ký Hiệp định Giơ-ne-vơ (21/7/1954), không phải hiệp định dẫn tới chiến thắng."
  ],
  "aliases": ["Điện Biên Phủ 1954", "chiến dịch Điện Biên Phủ", "chiến thắng Điện Biên Phủ 7/5/1954", "56 ngày đêm Điện Biên Phủ", "lừng lẫy năm châu chấn động địa cầu"],
  "topic_title": TOPIC_23,
  "lessons": [{"book": "NXBDG", "bai": 23}],
  "sources": [
   "https://vi.wikipedia.org/wiki/Chi%E1%BA%BFn_d%E1%BB%8Bch_%C4%90i%E1%BB%87n_Bi%C3%AAn_Ph%E1%BB%A7",
   "https://vi.wikipedia.org/wiki/K%E1%BA%BF_ho%E1%BA%A1ch_Navarre"
  ],
  "fixed": ["thẻ bổ sung: thẻ riêng cho Điện Biên Phủ 1954, phân biệt rõ với 'Điện Biên Phủ trên không' 12/1972"]
 },
])

for i, msgs in FIX.items():
    cards[i]['fixed'] = msgs

os.makedirs(OUT_DIR, exist_ok=True)
out_cards = [c for i, c in enumerate(cards) if i not in REJECT] + NEW_CARDS
json.dump({'grade': 12, 'chunk': 2, 'cards': out_cards},
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('IN:', len(cards), '| FIXED:', len(FIX), '| REJECT:', len(REJECT),
      '| NEW:', len(NEW_CARDS), '| OUT:', len(out_cards))
