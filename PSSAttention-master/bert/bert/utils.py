# -*- coding: utf-8 -*-
import numpy as np
import pickle
import os
import string
import codecs

from random import shuffle
from transformers import  BertTokenizer

# 用数据集最开始的n_padded条数据补到数据集最后使得数据集大小为batch size的整数倍
def pad_dataset(dataset, bs):
    n_records = len(dataset)
    n_padded = bs - n_records % bs
    new_dataset = [t for t in dataset]
    new_dataset.extend(dataset[:n_padded])
    return new_dataset

# # l用symbol(-1)补充句子“位置信息“(dist)到最大长度
# def pad_seq(dataset, field, max_len, symbol):
#     n_records = len(dataset)
#     for i in range(n_records):
#         assert isinstance(dataset[i][field], list)
#         while len(dataset[i][field]) < max_len:
#             dataset[i][field].append(symbol)
#     return dataset

# 从文件中读取数据，每句话有这些属性：sent, words, twords, wc, wct, dist, sid, beg, end
def read(path, tokenizer,max_len):
    dataset = []
    sid = 0 # id
    with open(path, encoding='utf-8') as fp:
        for line in fp:
            record = {} # 和这句话有关的y所有信息
            tokens = line.strip().split()
            words, target_words = [], [] # 存words in sentence和target words
            d = [] # 存位置信息
            find_label = False # 标签
            tmask =[0]  # target mask
            for t in tokens:

                # 说明是目标词 negative: 0, positive: 1, neutral: 2
                # 需要和evals里保持一致
                if '/p' in t or '/n' in t or '/0' in t:
                    end = 'xx'
                    y = 0
                    if '/p' in t:
                        end = '/p'
                        y = 1
                    elif '/n' in t:
                        end = '/n'
                        y = 0
                    elif '/0' in t:
                        end = '/0'
                        y = 2
                    # 将目标词加入words和target_words
                    words.append(t[:-2])
                    target_words.append(t[:-2])
                    # left_most和right_most分别记录了目标词的最左边和最右边的位置
                    if not find_label:
                        find_label = True
                        record['y'] = y
                        left_most = right_most = tokens.index(t)
                    else:
                        right_most += 1

                    # 记录分词长度产生mask 1
                    l = len(tokenizer.tokenize(t[:-2]))
                    tmask.extend([1]*(l))

                # 不是目标词，直接加入words
                else:
                    words.append(t)
                    l = len(tokenizer.tokenize(t))
                    tmask.extend([0]*(l))
            tmask.extend([0]*(max_len-len(tmask)))
            # 原始句子，去掉标签之后的整句话，目标词
            record['sent'] = line.strip()
            record['words'] = words.copy()
            record['twords'] = target_words.copy()
            # 句子长度， 目标词长度
            record['wc'] = len(words)  # word count
            record['wct'] = len(record['twords'])  # target word count
            # 这句话的id
            record['sid'] = sid
            # 目标词的开始和结束为止
            record['beg'] = left_most
            record['end'] = right_most + 1
            record['tmask']=tmask.copy()
            sid += 1
            dataset.append(record)
    return dataset


def get_bert_token(sent,tokenizer,max_len):
    # bert to word vector
    tokens = tokenizer.tokenize(sent)
    ids = tokenizer.encode(sent, max_length=max_len, pad_to_max_length=True)
    return tokens, ids, np.zeros_like(ids)

# 从文件中读取，处理数据，整理擦除信息，最多5次擦除
def load_data(data_rate, erase, tokenizer, ds_name, a1_name=None, a2_name=None, a3_name=None, a4_name=None, a5_name=None, erasing_or_final=True):
    train_file = './dataset/%s/train.txt' % ds_name
    test_file = './dataset/%s/test.txt' % ds_name
    max_len=96
    # 从文件读取数据，属性：sent, words, twords, wc, wct, dist, sid, beg, end
    train_set = read(train_file,tokenizer,max_len)
    test_set = read(test_file,tokenizer,max_len)
    #shuffle(train_set)
    train_set = train_set[:int(data_rate*len(train_set))]

    # 将词映射为词id，按词典映射，padding部分为0，添加属性：wids
    train_set = set_wid(dataset=train_set, max_len=max_len,tokenizer=tokenizer)
    test_set = set_wid(dataset=test_set, max_len=max_len,tokenizer=tokenizer)

    # 将目标词词映射为词id，按词典映射，padding部分为0，添加属性：tids
    train_set = set_tid(dataset=train_set, max_len=max_len,tokenizer=tokenizer)
    test_set = set_tid(dataset=test_set,  max_len=max_len,tokenizer=tokenizer)


    alphas1 = np.loadtxt(a1_name) if a1_name != None else None
    alphas2 = np.loadtxt(a2_name) if a2_name != None else None
    alphas3 = np.loadtxt(a3_name) if a3_name != None else None
    alphas4 = np.loadtxt(a4_name) if a4_name != None else None
    alphas5 = np.loadtxt(a5_name) if a5_name != None else None
    
    if erasing_or_final:
        # 利用擦除信息计算句子attention的mask，添加属性：mask
        train_set = get_attention_mask_forerasing(erase,dataset=train_set, alphas1=alphas1, alphas2=alphas2, alphas3=alphas3, alphas4=alphas4, alphas5=alphas5, a1_name=a1_name, a2_name=a2_name, a3_name=a3_name, a4_name=a4_name, a5_name=a5_name)
    else:
        # 利用擦除信息计算句子attention的mask和对应的value，添加属性：mask, amask, avalue
        train_set = get_attention_mask_final(erase,dataset=train_set, alphas1=alphas1, alphas2=alphas2, alphas3=alphas3, alphas4=alphas4, alphas5=alphas5, a1_name=a1_name, a2_name=a2_name, a3_name=a3_name, a4_name=a4_name, a5_name=a5_name)
    # 测试集不会有擦除信息，计算句子attention的mask，添加属性：mask
    test_set = get_attention_mask_fortest(dataset=test_set)
    
    # 属性：sent, words, twords, wc, wct, dist, sid, beg, end, pw, wids, tids, mask, (amask), (avalue)
    dataset = [train_set, test_set]

    return dataset


# 得到bert的词id,segment,添加属性：wids
def set_wid(dataset, max_len,tokenizer):
    n_records = len(dataset)
    for i in range(n_records):
        sent = dataset[i]['words']
        sent=' '.join(sent)
        dataset[i]['wtoken'],dataset[i]['wids'],dataset[i]['wseg'] = get_bert_token(sent,tokenizer,max_len)
    return dataset

# 得到bert的词id,segment,添加属性：tids
def set_tid(dataset, max_len,tokenizer):
    n_records = len(dataset)
    for i in range(n_records):
        sent = dataset[i]['twords']
        # 将目标词映射为词id，按词典映射，padding部分为0
        sent=' '.join(sent)
        dataset[i]['ttoken'],dataset[i]['tids'],dataset[i]['tseg'] = get_bert_token(sent,tokenizer,max_len)
    return dataset



# main.py中调用
def build_dataset(data_rate,erase,ds_name, bs, vocab_path, a1_name=None, a2_name=None, a3_name=None, a4_name=None, a5_name=None, erasing_or_final=True):
    tokenizer=BertTokenizer.from_pretrained(vocab_path)
    dataset = load_data(data_rate,erase,tokenizer,ds_name=ds_name, a1_name=a1_name, a2_name=a2_name, a3_name=a3_name, a4_name=a4_name, a5_name=a5_name, erasing_or_final=erasing_or_final) # 读取数据集和词典

    n_train = len(dataset[0]) # 训练集长度
    n_test = len(dataset[1]) # 测试集长度


    # 用数据集最开始的n_padded条数据补到数据集最后使得数据集大小为batch size的整数倍
    train_set = pad_dataset(dataset=dataset[0], bs=bs)
    test_set = pad_dataset(dataset=dataset[1], bs=bs)
    return [train_set, test_set],  n_train, n_test

# 利用擦除信息计算句子attention的mask，添加属性：mask，（修改wids）
def get_attention_mask_forerasing(erase,dataset, alphas1=None, alphas2=None, alphas3=None, alphas4=None, alphas5=None, a1_name=None, a2_name=None, a3_name=None, a4_name=None, a5_name=None):
    n_tuples = len(dataset)
    good_tuples = [0, 0, 0, 0, 0]
    bad_tuples = [0, 0, 0, 0, 0]
    max_entroy = erase
    
    for i in range(n_tuples):
        dataset[i]['mask'] = []
        dataset[i]['input_mask'] = []
        masks = [] # attention mask
        input_mask = [] # bert mask
        for w in dataset[i]['wids']:
            if w in {0}: # 0:PAD,101:CLS,102:SEP
                masks.append(0.0)
                input_mask.append(0.0)
            elif w in {101,102}:
                masks.append(0.0)
                input_mask.append(1.0)
            else:
                masks.append(1.0)
                input_mask.append(1.0)
    
        if a1_name != None:
            this_alpha = alphas1[i]
            this_alpha = this_alpha[this_alpha!=0]
            if - np.sum(np.log2(abs(this_alpha)) * abs(this_alpha)) < max_entroy:
                index = abs(alphas1[i]).argmax()
                masks[index] = 0.0 # erasing
                dataset[i]['wids'][index] = 0 # erasing
                if alphas1[i][index] > 0:
                    good_tuples[0] += 1
                else:
                    bad_tuples[0] += 1

        if a2_name != None:
            this_alpha = alphas2[i]
            this_alpha = this_alpha[this_alpha!=0]
            if - np.sum(np.log2(abs(this_alpha)) * abs(this_alpha)) < max_entroy:
                index = abs(alphas2[i]).argmax()
                masks[index] = 0.0 # erasing
                dataset[i]['wids'][index] = 0 # erasing
                if alphas2[i][index] > 0:
                    good_tuples[1] += 1
                else:
                    bad_tuples[1] += 1

        if a3_name != None:
            this_alpha = alphas3[i]
            this_alpha = this_alpha[this_alpha!=0]
            if - np.sum(np.log2(abs(this_alpha)) * abs(this_alpha)) < max_entroy:
                index = abs(alphas3[i]).argmax()
                masks[index] = 0.0 # erasing
                dataset[i]['wids'][index] = 0 # erasing
                if alphas3[i][index] > 0:
                    good_tuples[2] += 1
                else:
                    bad_tuples[2] += 1

        if a4_name != None:
            this_alpha = alphas4[i]
            this_alpha = this_alpha[this_alpha!=0]
            if - np.sum(np.log2(abs(this_alpha)) * abs(this_alpha)) < max_entroy:
                index = abs(alphas4[i]).argmax()
                masks[index] = 0.0 # erasing
                dataset[i]['wids'][index] = 0 # erasing
                if alphas4[i][index] > 0:
                    good_tuples[3] += 1
                else:
                    bad_tuples[3] += 1
    
        if a5_name != None:
            this_alpha = alphas5[i]
            this_alpha = this_alpha[this_alpha!=0]
            if - np.sum(np.log2(abs(this_alpha)) * abs(this_alpha)) < max_entroy:
                index = abs(alphas5[i]).argmax()
                masks[index] = 0.0 # erasing
                dataset[i]['wids'][index] = 0 # erasing
                if alphas5[i][index] > 0:
                    good_tuples[4] += 1
                else:
                    bad_tuples[4] += 1
    
        dataset[i]['mask'].extend(masks)
        dataset[i]['input_mask'].extend(input_mask)

    print ("Erasing ratio:")
    print ("1: good: %.2f, bad: %.2f" % (float(good_tuples[0]) / n_tuples, float(bad_tuples[0]) / n_tuples))
    print ("2: good: %.2f, bad: %.2f" % (float(good_tuples[1]) / n_tuples, float(bad_tuples[1]) / n_tuples))
    print ("3: good: %.2f, bad: %.2f" % (float(good_tuples[2]) / n_tuples, float(bad_tuples[2]) / n_tuples))
    print ("4: good: %.2f, bad: %.2f" % (float(good_tuples[3]) / n_tuples, float(bad_tuples[3]) / n_tuples))
    print ("5: good: %.2f, bad: %.2f" % (float(good_tuples[4]) / n_tuples, float(bad_tuples[4]) / n_tuples))
    
    return dataset


# 利用擦除信息计算句子attention的mask和对应的value，添加属性：mask, amask, avalue
def get_attention_mask_final(erase,dataset, alphas1=None, alphas2=None, alphas3=None, alphas4=None, alphas5=None, a1_name=None, a2_name=None, a3_name=None, a4_name=None, a5_name=None):
    n_tuples = len(dataset)
    good_tuples = [0, 0, 0, 0, 0]
    bad_tuples = [0, 0, 0, 0, 0]
    max_entroy = erase
    
    for i in range(n_tuples):
        dataset[i]['mask'] = []
        dataset[i]['input_mask'] = []
        dataset[i]['amask'] = []
        dataset[i]['avalue'] = []
        
        masks = [] # attention mask
        amasks = [] # 擦除需要监督的部分
        avalues = [] # 擦除需要监督的部分的监督值
        input_mask = [] # bert mask
        for w in dataset[i]['wids']:
            if w in {0}: # 0:PAD,101:CLS,102:SEP
                masks.append(0.0)
                input_mask.append(0.0)
            elif w in {101,102}:
                masks.append(0.0)
                input_mask.append(1.0)
            else:
                masks.append(1.0)
                input_mask.append(1.0)
            amasks.append(0.0)
            avalues.append(0.0)
        
        if a1_name != None:
            this_alpha = alphas1[i]
            this_alpha = this_alpha[this_alpha!=0]
            if - np.sum(np.log2(abs(this_alpha)) * abs(this_alpha)) < max_entroy:
                index = abs(alphas1[i]).argmax()
                amasks[index] = 1.0
                if alphas1[i][index] > 0:
                    avalues[index] = 1.0 # 正确分类监督值为1，否则为0
                    good_tuples[0] += 1
                else:
                    bad_tuples[0] += 1

        if a2_name != None:
            this_alpha = alphas2[i]
            this_alpha = this_alpha[this_alpha!=0]
            if - np.sum(np.log2(abs(this_alpha)) * abs(this_alpha)) < max_entroy:
                index = abs(alphas2[i]).argmax()
                amasks[index] = 1.0
                if alphas2[i][index] > 0:
                    avalues[index] = 1.0 # 正确分类监督值为1，否则为0
                    good_tuples[1] += 1
                else:
                    bad_tuples[1] += 1
    
        if a3_name != None:
            this_alpha = alphas3[i]
            this_alpha = this_alpha[this_alpha!=0]
            if - np.sum(np.log2(abs(this_alpha)) * abs(this_alpha)) < max_entroy:
                index = abs(alphas3[i]).argmax()
                amasks[index] = 1.0
                if alphas3[i][index] > 0:
                    avalues[index] = 1.0 # 正确分类监督值为1，否则为0
                    good_tuples[2] += 1
                else:
                    bad_tuples[2] += 1

        if a4_name != None:
            this_alpha = alphas4[i]
            this_alpha = this_alpha[this_alpha!=0]
            if - np.sum(np.log2(abs(this_alpha)) * abs(this_alpha)) < max_entroy:
                index = abs(alphas4[i]).argmax()
                amasks[index] = 1.0
                if alphas4[i][index] > 0:
                    avalues[index] = 1.0 # 正确分类监督值为1，否则为0
                    good_tuples[3] += 1
                else:
                    bad_tuples[3] += 1
    
        if a5_name != None:
            this_alpha = alphas5[i]
            this_alpha = this_alpha[this_alpha!=0]
            if - np.sum(np.log2(abs(this_alpha)) * abs(this_alpha)) < max_entroy:
                index = abs(alphas5[i]).argmax()
                amasks[index] = 1.0
                if alphas5[i][index] > 0:
                    avalues[index] = 1.0 # 正确分类监督值为1，否则为0
                    good_tuples[4] += 1
                else:
                    bad_tuples[4] += 1
    
        dataset[i]['mask'].extend(masks)
        dataset[i]['input_mask'].extend(input_mask)
        dataset[i]['amask'].extend(amasks)
        dataset[i]['avalue'].extend(avalues)
    
    print ("Erasing ratio:")
    print ("1: good: %.2f, bad: %.2f" % (float(good_tuples[0]) / n_tuples, float(bad_tuples[0]) / n_tuples))
    print ("2: good: %.2f, bad: %.2f" % (float(good_tuples[1]) / n_tuples, float(bad_tuples[1]) / n_tuples))
    print ("3: good: %.2f, bad: %.2f" % (float(good_tuples[2]) / n_tuples, float(bad_tuples[2]) / n_tuples))
    print ("4: good: %.2f, bad: %.2f" % (float(good_tuples[3]) / n_tuples, float(bad_tuples[3]) / n_tuples))
    print ("5: good: %.2f, bad: %.2f" % (float(good_tuples[4]) / n_tuples, float(bad_tuples[4]) / n_tuples))
    
    return dataset

# 计算句子attention的mask，添加属性：mask
def get_attention_mask_fortest(dataset):
    n_tuples = len(dataset)
    for i in range(n_tuples):
        dataset[i]['mask'] = []
        dataset[i]['input_mask'] = []
        masks = []
        input_mask = []
        for w in dataset[i]['wids']:
            if w == 0: # 0是padding的部分
                masks.append(0.0)
                input_mask.append(0.0)
            elif w in {101,102}:
                masks.append(0.0)
                input_mask.append(1.0)
            else:
                masks.append(1.0)
                input_mask.append(1.0)
        dataset[i]['mask'].extend(masks)
        dataset[i]['input_mask'].extend(input_mask)
    return dataset
