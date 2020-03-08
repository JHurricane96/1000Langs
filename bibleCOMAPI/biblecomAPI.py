__author__ = "Ehsaneddin Asgari"
__license__ = "Apache 2"
__version__ = "1.0.0"
__maintainer__ = "Ehsaneddin Asgari"
__website__ = "https://llp.berkeley.edu/asgari/"
__git__ = "https://github.com/ehsanasgari/"
__email__ = "ehsan.asgari@gmail.com"
__project__ = "1000Langs -- Super parallel project at CIS LMU"

import requests
from bs4 import BeautifulSoup
import tqdm
import sys
sys.path.append('../')
from utility.file_utility import FileUtility
import pandas as pd
from metaAPI.metadata import getMetaMerged
from multiprocessing import Pool
from biblecrawler.bibleCOM import BibleCom

class BibleComAPl(object):
    '''
        PBC retrieving from the bible com
    '''
    def __init__(self, output_path):
        '''
            Constructor
        '''
        # set the parameters
        self.output_path = output_path
        FileUtility.ensure_dir(self.output_path + '/biblecom_intermediate/')
        FileUtility.ensure_dir(self.output_path + '/reports/')
        

    def crawl_bpc(self,nump=20,update_meta=False, override=False, repeat=1):
        # update the metadata table
        if update_meta:
            self.update_meta_data(nump)
        # read the metadata table
        self.df_biblecom=pd.read_table('../meta/biblecom.tsv', sep='\t')
        urliso=self.df_biblecom[['url','language_iso']].values.tolist()
        
        if not override:
            new_list=[]
            for url, iso in urliso:
                num=url.split('/')[0:-1][-1]
                if not FileUtility.exists(self.output_path+'/'+iso+'_'+num+'.biblecom.txt'):
                    new_list.append([url,iso])
            urliso=new_list
        res=BibleComAPl.make_parallel(min(nump,len(urliso)),self.crawl_a_lang,urliso)
        
        # iterating for max coverage
        count = 0
        while count < repeat:
            # update list
            new_list=[]
            for url, iso in urliso:
                num=url.split('/')[0:-1][-1]
                if not FileUtility.exists(self.output_path+'/'+iso+'_'+num+'.biblecom.txt'):
                    new_list.append([url,iso])
            if len(new_list) == 0:
                break
            count += 1
            urliso=new_list
            print ('Double check for the missing translations..')
            res=BibleComAPl.make_parallel(min(nump,len(urliso)),self.crawl_a_lang,urliso)
        
        self.create_report_biblecom()
        
    def crawl_a_lang(self, urlmeta):
        url,iso=urlmeta
        num=url.split('/')[0:-1][-1]
        BB=BibleCom((url,self.output_path + '/biblecom_intermediate/','../'+iso+'_'+num+'.biblecom.txt'))
        return url,True
        
    def update_meta_data(self, nump):
        '''
        metadata updating
        '''
        res=BibleComAPl.make_parallel(nump,self.find_meta_data,self.find_all_bibles_biblecom().items())
        res.pop('https://www.bible.com/versions', None)
        res_list = [bible for bible in res.values() if bible]
        df=pd.DataFrame(res_list).rename(index=str,columns={idx:val for idx,val in enumerate(['url','language_iso','Description','Year','language_name','trans_ID'])})
        df=df.set_index('url')
        df.to_csv('../meta/biblecom.tsv', sep='\t', index=True)

    def get_metadata(self, node):
        '''
        part of meta data extraction
        '''
        num_description = node.attrs['href'][len('/versions/'):].split('-')
        num = num_description[0]
        description = ' '.join(num_description[1:])
        return description, num

    def find_all_bibles_biblecom(self):
        '''
        part of meta data extraction
        '''
        base_url = 'https://www.bible.com/versions'
        soup = BeautifulSoup(requests.get(base_url).content)
        # collect the game ids
        collect_version_links=dict()
        for lang_link in soup.select('a[href^="/languages/"]'):
            iso = lang_link.attrs['href'][len('/languages/'):]
            lang = str(lang_link.contents[0].string)
            link = lang_link.next_sibling
            while link != None and link.attrs.get('href', '').startswith('/versions/'):
                descript,num=self.get_metadata(link)
                collect_version_links['https://www.bible.com'+link.attrs['href']]=(iso,descript,num,lang,num)
                link = link.next_sibling
        return collect_version_links

    def find_meta_data(self, urlmeta):
        '''
        part of meta data extraction
        '''
        url,meta=urlmeta
        soup_inner = BeautifulSoup(requests.get(url).content)
        for link in soup_inner.select('a[href^="/bible/"]'):
            if link.attrs.get('role', None) == 'button':
                return url,(['https://www.bible.com'+link.attrs['href']]+list(meta))
        return url, False

    @staticmethod
    def make_parallel(num_p, func, in_list):
        pool = Pool(processes=num_p)
        final_res = dict()
        for idx, res in tqdm.tqdm(pool.imap_unordered(func, in_list, chunksize=num_p), total=len(in_list)):
            final_res[idx] = res
        pool.close()
        return final_res

    def create_report_biblecom(self):
        self.df_biblecom['verses']=0

        biblecom_files=FileUtility.recursive_glob(self.output_path+'/', '*.biblecom.txt')
        for bib_file in biblecom_files:
            file_parts = bib_file.split('/')[-1].split('.')[0:-1][0:-1][-1].split('_')
            num_file_parts = len(file_parts)
            if num_file_parts == 2:
                iso, code = file_parts
            elif num_file_parts == 3:
                iso = "_".join(file_parts[:2])
                code = file_parts[2]
            else:
                continue
            length=len(FileUtility.load_list(bib_file))
            self.df_biblecom.loc[:,'verses'][(self.df_biblecom['language_iso']==iso) & (self.df_biblecom['trans_ID']==int(code))]=length
        self.df_biblecom.set_index('trans_ID')
        self.df_biblecom.to_csv(self.output_path + '/reports/crawl_report_biblecom.tsv', sep='\t', index=False, columns=['language_iso','trans_ID','language_name','verses'])
        self.generate_final_rep()

    def generate_final_rep(self):
        rep_files=FileUtility.recursive_glob(self.output_path+'/reports/','crawl_report_*.tsv')
        df_s=[]
        for report_file in rep_files:
            version=report_file.split('/')[-1].split('.')[0].split('_')[-1]
            temp=pd.read_table(report_file)[['trans_ID','language_iso','language_name','verses']]
            temp['source']=version
            df_s.append(temp.copy())
        df_s=pd.concat(df_s)
        df_s.set_index('trans_ID')
        self.aggregated_rep=df_s
        df_s.to_csv(self.output_path + '/reports/final_rep.tsv', sep='\t', index=False, columns=['language_iso','trans_ID','language_name','verses','source'])

