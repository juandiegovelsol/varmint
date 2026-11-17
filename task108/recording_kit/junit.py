import sys, xml.etree.ElementTree as ET
tot=0; bad=[]
for f in sys.argv[1:]:
    for tc in ET.parse(f).getroot().iter('testcase'):
        tot+=1
        if tc.find('failure') is not None or tc.find('error') is not None:
            bad.append(tc.get('classname','').split('/')[-1]+' :: '+tc.get('name'))
print(f'  total={tot} failed={len(bad)}')
for b in bad: print('   x', b)
