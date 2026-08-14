import pandas as pd
import numpy as np

def get_class_info(class_df):
  class_info = {}
  class_name = class_df.iloc[0, 0].split(":")[0]

  days_raw = str(class_df.iloc[1, 1])
  class_days = list(days_raw)

  class_start = class_df.iloc[2, 0].split()[0]
  class_end = class_df.iloc[2, 0].split()[-1]
  class_loc = class_df.iloc[3, 0]

  class_info = {
      "name": class_name,
      "days": class_days,
      "start": class_start,
      "end": class_end,
      "location": class_loc,
  }
  return class_info

def import_and_format(test_data_fpath):
    test_data = pd.read_csv(
        test_data_fpath,
        sep="\t"
    ).reset_index()
    test_data.loc[len(test_data)] = np.nan
    test_data = test_data.shift(1)
    test_data.iloc[0, 0] = test_data.columns[-1]
    test_data.columns = range(len(test_data.columns))
    test_data = test_data.drop(columns=[1, 2, 3, 5, 6, 7, 8, 9])
    test_data.columns = range(len(test_data.columns))
    test_data = test_data[(~test_data[0].str.contains("Note", na=False)) & (test_data[0].notna())].reset_index(drop=True)

    return test_data

def class_data(test_data):
    test_data_dict = {
        f"class_{i}": test_data.loc[(i - 1) * 5 : ((i - 1) * 5) + 4]
        for i in range(1, (len(test_data) // 5)+1)
    }
    for class_num, class_df in test_data_dict.items():
        test_data_dict[class_num] = get_class_info(class_df)

    return test_data_dict

test_data_fpath = "/Users/danielgarcia-barnett/Desktop/Coding/calendar_mngr/data/test_data/input/test.txt"
test_data = import_and_format(test_data_fpath)
test_data_dict = class_data(test_data)
