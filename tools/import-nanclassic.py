"""난처한 클래식 수록 음악 HTML을 listening-data.js로 바꾼다.

쓰는 법:
    python3 tools/import-nanclassic.py 난처한클래식.html listening-data.js

입력 HTML은 난톡 게시판에서 모은 '난처한 클래식 · 수록 음악 듣기' 페이지다.
권(section) 안에 중요곡 모음(.comp)과 스피커 번호별 글(.row)이 들어 있다.
"""
import json
import re
import sys
from html.parser import HTMLParser

# 권 번호 -> 그 권에서 다루는 작곡가(study-data.js의 short 이름)
BOOK_COMPOSERS = {
    1: ['모차르트'],
    2: ['베토벤'],
    3: ['바흐'],
    4: ['헨델'],
    5: ['쇼팽', '리스트'],
    6: ['베르디', '바그너'],
    7: ['슈만', '브람스', '클라라 슈만'],
    8: ['차이콥스키'],
    9: ['드뷔시'],
    10: [],
}


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sections = []
        self.section = None
        self.comp = None
        self.item = None
        self.capture = None
        self.buffer = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get('class', '')
        if tag == 'section':
            self.section = {'title': '', 'comps': [], 'rows': []}
            self.sections.append(self.section)
        elif self.section is None:
            return
        elif tag == 'h2':
            self.start('h2')
        elif tag == 'div' and cls == 'comp':
            self.comp = {'name': '', 'post': '', 'items': []}
            self.section['comps'].append(self.comp)
        elif tag == 'span' and cls == 'compname':
            self.start('compname')
        elif tag == 'div' and cls in ('sub', 'row'):
            self.item = {'label': '', 'title': '', 'url': '', 'post': '', 'kind': cls}
            if cls == 'sub':
                self.comp['items'].append(self.item)
            else:
                self.section['rows'].append(self.item)
                self.comp = None
        elif tag == 'span' and cls == 'lab':
            self.start('label')
        elif tag == 'a' and 'song' in cls:
            self.item['url'] = attrs.get('href', '')
            self.start('title')
        elif tag == 'span' and cls == 'nolink':
            self.start('title')
        elif tag == 'a' and cls == 'orig':
            if self.item is not None and self.item['kind'] == 'row':
                self.item['post'] = attrs.get('href', '')
            elif self.comp is not None:
                self.comp['post'] = attrs.get('href', '')

    def start(self, what):
        self.capture = what
        self.buffer = ''

    def handle_endtag(self, tag):
        if not self.capture or tag not in ('h2', 'span', 'a'):
            return
        text = re.sub(r'\s+', ' ', self.buffer).strip()
        if self.capture == 'h2':
            self.section['title'] = text
        elif self.capture == 'compname':
            self.comp['name'] = text
        elif self.capture == 'label':
            self.item['label'] = text
        elif self.capture == 'title':
            self.item['title'] = text
        self.capture = None

    def handle_data(self, data):
        if self.capture:
            self.buffer += data


def tidy(title):
    title = title.replace('<', '〈').replace('>', '〉')
    title = re.sub(r'\s*\(목록 링크\)$', '', title)
    return re.sub(r'\s+', ' ', title).strip()


def plain(title):
    """곡 이름 비교용: 띄어쓰기 · 괄호 · 따옴표를 뺀다."""
    return re.sub(r'[\s〈〉<>《》「」『』\'"‘’“”·,.()]', '', title).lower()


def parse_track(item):
    """스피커 번호 · 쪽수 · 곡명을 나눈다. 번호를 못 찾으면 no는 None."""
    label, title = item['label'], item['title']
    page = ''
    match = re.fullmatch(r'스피커 0*(\d+)번', label)
    if match:
        return int(match.group(1)), label, page, tidy(title)
    # QR 갱신본: "스피커 4번 (p.81) : 〈미제레레〉"
    match = re.match(r'스피커 0*(\d+)번\s*\(p\.(\d+)\)\s*:\s*(.*)', title)
    if match:
        return int(match.group(1)), '스피커 %s번' % match.group(1), 'p.' + match.group(2), tidy(match.group(3))
    # "10권 스피커 048번 ○○, 049번 : △△" 처럼 두 곡을 한 글에 묶은 경우
    match = re.match(r'\d+권 스피커 0*(\d+)번 (.*?), 0*(\d+)번\s*:\s*(.*)', title)
    if match:
        return int(match.group(1)), '스피커 %s·%s번' % (match.group(1), match.group(3)), page, tidy(match.group(2) + ' · ' + match.group(4))
    # "2권 스피커 01번 ~ 04번 : ○○", "4권 스피커 37권 : ○○"(원글의 오타)
    match = re.match(r'\d+권 스피커 0*(\d+)(?:번|권)?\s*(?:~\s*0*(\d+)번)?\s*:\s*(.*)', title)
    if match:
        first, last = match.group(1), match.group(2)
        shown = '스피커 %s–%s번' % (first, last) if last else '스피커 %s번' % first
        return int(first), shown, page, tidy(match.group(3))
    match = re.match(r'(.*?삽입곡)\s*:\s*(.*)', title)
    if match:
        return None, '콘서트 프리뷰', page, tidy(match.group(2))
    return None, label, page, tidy(title)


def build(sections):
    books = []
    for index, section in enumerate(sections):
        match = re.match(r'(\d+)권 · (.*?)\s+(\d+)개 글$', section['title'])
        if match:
            number, name, posts = int(match.group(1)), match.group(2), int(match.group(3))
        else:
            number, name, posts = None, re.sub(r'\s+\d+개 글$', '', section['title']), len(section['rows'])
        book = {
            'id': str(number) if number else 'etc',
            'number': number,
            'name': name,
            'posts': posts,
            'composers': BOOK_COMPOSERS.get(number, []),
            'key': [],
            'keyPosts': [],
            'playlists': [],
            'tracks': [],
        }
        # 중요곡: 1권은 쪽수가 있는 2023 갱신본만, 10권은 ①②를 번호순으로 합친다.
        comps = section['comps']
        if any('갱신본' in comp['name'] for comp in comps):
            comps = [comp for comp in comps if '갱신본' in comp['name']]
        for comp in comps:
            if comp['post']:
                book['keyPosts'].append(comp['post'])
            for item in comp['items']:
                no, label, page, title = parse_track(item)
                if no is None and ('재생' in title or 'playlist' in item['url']):
                    book['playlists'].append({'title': title, 'url': item['url']})
                    continue
                book['key'].append({'no': no, 'label': label, 'page': page, 'title': title, 'url': item['url']})
        book['key'].sort(key=lambda track: (track['no'] is None, track['no'] or 0))
        for item in section['rows']:
            no, label, page, title = parse_track(item)
            book['tracks'].append({'no': no, 'label': label, 'page': page, 'title': title, 'url': item['url'], 'post': item['post']})
        # 중요곡 번호가 원글에서 잘못 적힌 경우(예: 1권 레퀴엠이 59번)를 곡 이름이 같은 수록곡 번호로 바로잡는다.
        by_title = {plain(track['title']): track for track in book['tracks'] if track['no'] is not None}
        for track in book['key']:
            same = by_title.get(plain(track['title']))
            if same and same['no'] != track['no']:
                track['no'], track['label'] = same['no'], same['label']
        book['key'].sort(key=lambda track: (track['no'] is None, track['no'] or 0))
        # 중요곡에 있는 쪽수를 같은 번호의 수록곡에도 붙인다.
        pages = {track['no']: track['page'] for track in book['key'] if track['page']}
        for track in book['tracks']:
            if not track['page'] and track['no'] in pages:
                track['page'] = pages[track['no']]
        books.append(book)
    return books


def main():
    source, target = sys.argv[1], sys.argv[2]
    page = Page()
    with open(source, encoding='utf-8') as handle:
        page.feed(handle.read())
    books = build(page.sections)
    data = {
        'source': '난처한 클래식 · 난톡 게시판 「수록 음악 듣기」 모음',
        'books': books,
    }
    with open(target, 'w', encoding='utf-8') as handle:
        handle.write('// 난처한 클래식 수록 음악 목록. tools/import-nanclassic.py로 만든다.\n')
        handle.write('window.CLASSIC_LISTENING_DATA = ' + json.dumps(data, ensure_ascii=False, indent=2) + ';\n')
    for book in books:
        print('%-10s 수록곡 %3d · 중요곡 %2d · 재생목록 %d' % (book['id'] + ' ' + book['name'], len(book['tracks']), len(book['key']), len(book['playlists'])))


if __name__ == '__main__':
    main()
