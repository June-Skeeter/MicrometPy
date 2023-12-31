import os
import numpy as np
import pandas as pd
import configparser
import argparse
import datetime

class Write():
    def __init__(self,ini):#,ini='WriteTraces.ini'):
               
        # Create a config file based on the job (Write vs. Read; standard vs. custom)
        self.ini = configparser.ConfigParser()
        self.ini.read('../MicrometPy.ini')
        self.ini.read(ini)
    
    def dateIndex(self):
        Date_cols = [i for i in self.ini[self.Site_File]['Date_Cols'].split(',')]
        if self.ini[self.Site_File]['Date_Fmt'] == 'Auto':
            Date_col = Date_cols[0]
            self.Data[Date_col] = pd.DatetimeIndex(self.Data[Date_col])
            self.Data = self.Data.set_index(Date_col)

        else:
            self.Data['Timestamp'] = ''
            for col in self.ini[self.Site_File]['Date_Cols'].split(','):
                ix = self.ini[self.Site_File]['Header_list'].split(',').index(col)
                unit = self.ini[self.Site_File]['Header_units'].split(',')[ix]
                if unit.upper() == 'HHMM':
                    self.Data.loc[self.Data[col]==2400,col]=0
                self.Data['Timestamp'] = self.Data['Timestamp'].str.cat(self.Data[col].astype(str).str.zfill(len(unit)),sep='')
            self.Data['Timestamp'] = pd.to_datetime(self.Data['Timestamp'],format=self.ini[self.Site_File]['Date_Fmt'])
            self.Data = self.Data.set_index('Timestamp')
        self.Data=self.Data.resample('30T').first()

    def FullYear(self):
        for self.y in self.Data.index.year.unique():
            self.Year = pd.DataFrame(data={'Timestamp':pd.date_range(start = f'{self.y}01010030',end=f'{self.y+1}01010001',freq='30T')})
            self.Year = self.Year.set_index('Timestamp')
            self.Year = self.Year.join(self.Data)
            
            d_1970 = datetime.datetime(1970,1,1,0,0)
            self.Year['Floor'] = self.Year.index.floor('D')
            self.Year['Secs'] = ((self.Year.index-self.Year['Floor']).dt.seconds/ (24.0 * 60.0 * 60.0))
            self.Year['Days'] = ((self.Year.index-d_1970).days+int(self.ini['Database']['datenum_base']))

            self.Year[self.ini['Database']['Timestamp']] = self.Year['Secs']+self.Year['Days']
            self.Year = self.Year.drop(columns=['Floor','Secs','Days'])
            self.Write()
    
    def Write(self):
        self.write_dir = self.ini['Paths']['database'].replace('YEAR',str(self.y)).replace('SITE',self.site_name)+self.ini[self.Site_File]['subfolder']

        if os.path.isdir(self.write_dir)==False:
            print('Creating new directory at:\n', self.write_dir)
            os.makedirs(self.write_dir)

        for T in self.Year.columns:
            if T == self.ini['Database']['Timestamp']:
                fmt = self.ini['Database']['Timestamp_dtype']
            else:
                fmt = self.ini['Database']['Trace_dtype']
            Trace = self.Year[T].astype(fmt).values
            if self.ini[self.Site_File]['Tag']!='' and T != self.ini['Database']['Timestamp']:
                T += '_' + self.ini[self.Site_File]['Tag']
            with open(f'{self.write_dir}/{T}','wb') as out:
                Trace.tofile(out)


class MakeTraces(Write):
    def __init__(self,ini='WriteTraces.ini'):
        super().__init__(ini)
        for self.Site_File in self.ini['Input']['Files'].split(','):
            self.site_name = self.ini[self.Site_File]['Site']
            self.findFiles()

    def findFiles(self):
        patterns = self.ini[self.Site_File]['path_patterns'].split(',')
        self.Data = pd.DataFrame()
        self.Metadata = pd.DataFrame()
        for dir,_,files in os.walk(self.ini['Paths']['datadump'].replace('SITE',self.site_name)):
            for file in (files):
                fn = f"{dir}/{file}"
                if len([p for p in patterns if p not in fn])==0:
                    if self.ini[self.Site_File]['Subtable_id'] == '':
                        self.readSingle(fn)
                    else:
                        self.readSubTables(fn)
        self.dateIndex()
        if self.ini[self.Site_File]['Exclude'] != '':
            self.Metadata = self.Metadata.drop(columns=self.ini[self.Site_File]['Exclude'].split(','))     
            self.Data = self.Data.drop(columns=self.ini[self.Site_File]['Exclude'].split(','))
        self.FullYear()

    def readSingle(self,fn):
        if self.ini[self.Site_File]['Header_Row'] != '':
            header = pd.read_csv(fn,skiprows=int(self.ini[self.Site_File]['Header_Row']),nrows=int(self.ini[self.Site_File]['First_Data_Row'])-int(self.ini[self.Site_File]['Header_Row']))
            self.Metadata = pd.concat([self.Metadata,header],axis=0)
            headers = header.columns
        else:
            headers = self.ini[self.Site_File]['Header_list'].split(',')
            units = self.ini[self.Site_File]['Header_units'].split(',')
            header = pd.DataFrame(columns=headers)
            header.iloc[0] = units
            self.Metadata = pd.concat([self.Metadata,header],axis=0)
        Data = pd.read_csv(fn,skiprows=int(self.ini[self.Site_File]['First_Data_Row']),header=None)
        Data.columns=headers
        self.Data = pd.concat([self.Data,Data],axis=0)

    def readSubTables(self,fn):
        # Read the file - if the first row is corrupted, it will be dropped
        try:
            Data = pd.read_csv(fn,header=None,na_values=[-6999,6999])
        except:
            Data = pd.read_csv(fn,header=None,na_values=[-6999,6999],skiprows=1)
            First = pd.read_csv(fn,header=None,na_values=[-6999,6999],nrows=1)
            pass
        for Subtable_id,headers,units in zip(self.ini[self.Site_File]['Subtable_id'].split('|'),self.ini[self.Site_File]['Header_list'].split('|'),self.ini[self.Site_File]['Header_units'].split('|')):
            headers = headers.split(',')
            units = units.split(',')
            if Data.shape[1]<len(headers):
                headers = headers[:Data.shape[1]]
                units = units[:Data.shape[1]]
            header = pd.DataFrame(columns=headers,data=[units],index=[0])
            header.iloc[0] = units
            
            self.col_num = headers.index('Subtable_id')
            Subtable = Data.loc[Data[self.col_num].astype(str)==Subtable_id]
            Subtable = Subtable[Subtable.columns[0:len(headers)]]
            drop = []
            for i,v in enumerate(headers):
                if v == '_':
                    drop.append(i)
            try:
                header = header.drop(columns=['_'])
            except:
                pass
            self.Metadata = pd.concat([self.Metadata,header],axis=0)
            Subtable = Subtable.drop(columns=drop)
            Subtable.columns=header.columns
            self.Data = pd.concat([self.Data,Subtable],axis=0)
        

class GSheetDump(Write):
    def __init__(self, ini='WriteTraces_Gsheets.ini'):
        super().__init__(ini)
        for self.Site_File in self.ini['Input']['Files'].split(','):
            self.site_name = self.ini[self.Site_File]['Site']
            self.readSheet()

    def readSheet(self):
        self.Metadata=pd.DataFrame()
        i = int(self.ini[self.Site_File]['subtable_id'])
        self.Data = pd.read_html(self.ini[self.Site_File]['path_patterns'],
                     skiprows=int(self.ini[self.Site_File]['Header_Row']))[i]
        self.dateIndex()
        if self.ini[self.Site_File]['Exclude'] != '':
            try:
                self.Metadata = self.Metadata.drop(columns=self.ini[self.Site_File]['Exclude'].split(','))     
            except:
                print('No Metadata?')
                pass
            self.Data = self.Data.drop(columns=self.ini[self.Site_File]['Exclude'].split(','))
        self.FullYear()

        


if __name__ == '__main__':
    file_path = os.path.split(__file__)[0]
    os.chdir(file_path)

    CLI=argparse.ArgumentParser()
    CLI.add_argument(
    "--ini",  # name on the CLI - drop the `--` for positional/required parameters
    nargs=1,  # 0 or more values expected => creates a list
    type=str,
    default='WriteTraces.ini',  # default if nothing is provided
    )
    
    args = CLI.parse_args()
    MakeTraces(args.ini)