from threading import Thread

class Module(Thread):
    print('module test')

    def __init__(self):
        print('init')
        
    def test(self):
        print('test')
