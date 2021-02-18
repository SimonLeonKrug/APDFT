from pyscf import gto, scf
from pyscf.symm.geom import detect_symm #change TOLERANCE to higher values
import numpy as np

elements = {'H':1, 'He':2,
'Li':3, 'Be':4, 'B':5, 'C':6, 'N':7, 'O':8, 'F':9, 'Ne':10,
'Na':11, 'Mg':12, 'Al':13, 'Si':14, 'P':15, 'S':16, 'Cl':17, 'Ar':18,
'K':19, 'Ca':20, 'Ga':31, 'Ge':32, 'As':33, 'Se':34, 'Br':35, 'Kr':36,
'Sc':21, 'Ti':22, 'V':23, 'Cr':24, 'Mn':25, 'Fe':26, 'Co':27, 'Ni':28, 'Cu':29, 'Zn':30,}

tolerance = 4 #Rounding to three digits

def delta(i,j):
    #Kronecker Delta
    if i == j:
        return 1
    else:
        return 0

def center_mole(mole):
    #Centers a molecule
    sum = (0,0,0)
    N = len(mole)
    for i in range(N):
        sum = np.add(mole[i][1],sum)
    sum = np.multiply(sum, 1/N)
    for i in range(N):
        mole[i][1] = np.subtract(mole[i][1],sum)

def Coulomb_matrix(mole):
    #returns the Coulomb matrix of a given molecule
    N = len(mole)
    result = np.zeros((N,N))
    for i in range(N):
        for j in range(N):
            if (j == i):
                result[i][i] = pow(elements[mole[i][0]], 2.4)
            else:
                result[i][j] = elements[mole[i][0]]*elements[mole[j][0]]/np.linalg.norm(np.subtract(mole[i][1],mole[j][1]))
    return result

def Coulomb_neighborhood(mole):
    '''returns the sum over rows/columns of the Coulomb matrix.
    Thus, each atom is assigned its Coulombic neighborhood'''
    matrix = Coulomb_matrix(mole)
    return matrix.sum(axis = 0)

def charge_inertia_tensor(mole):
    #Calculate an inertia tensor but with charges instead of masses
    N = len(mole)
    result_tensor = np.zeros((3,3))
    sum = 0
    for i in range(3):
        for j in range(i+1):
            for k in range(N):
                sum += elements[mole[k][0]]*(np.dot(mole[k][1], mole[k][1])*delta(i,j) - mole[k][1][i]*mole[k][1][j])
            result_tensor[i][j] = sum
            result_tensor[j][i] = sum
            sum = 0
    return result_tensor

def charge_inertia_moment(mole):
    #Calculate the inertia moments of a molecule with charges instead of masses
    #and sort them in ascending order
    w,v = np.linalg.eig(charge_inertia_tensor(mole))
    #Only the eigen values are needed, v is discarded
    return np.sort(w)

def num_AEchildren(mole, m = 2, dZ = [+1,-1]):
    '''Returns the number of alchemical enantiomers of mole that can be reached by
    varying m atoms in mole with identical Coulombic neighborhood by the values
    specified in dZ'''
    N = len(mole)
    z = len(dZ)
    if N < m:
        raise ValueError("Number of changing atoms must not exceed number of atoms in molecule")
    if z < 1:
        raise ValueError("Number of elements of dZ must be at least 1")
    if 0 in dZ:
        raise ValueError("0 is not allowed in dZ")
    #Find the Coulombic neighborhood of each atom in mole
    CN = Coulomb_neighborhood(mole)
    '''To make life easier, the values in CN are rounded to tolerance for easier comparison'''
    for i in range(N):
        CN[i] = round(CN[i],tolerance)
    '''Are there atoms with identical/close Coulombic neighborhood? Find them and store
    their indices'''
    similars = [np.where(CN == i)[0].tolist() for i in np.unique(CN)]
    print(similars)
    '''This is the list of all atoms which can be transmuted simultaneously.
    Now, count all AEs which are possible'''
    count = 0
    new_m = m
    for alpha in range(len(similars)):
        num_sites = len(similars[alpha])
        #Get necessary atoms listed in similars[alpha]
        '''Take all the indices in similars[alpha] and extract exactly those atoms from mole'''
        #Make sure, that m does no exceed length of similars[alpha] = num_sites
        if m > len(similars[alpha]):
            new_m = num_sites
            print("Warning: Number of changing atoms (", m, ") exceeds the number of alchemically similar sites in set", alpha, "which is", num_sites)
        else:
            new_m = m




# The order in which the atoms are presented constitutes their ID
benzene = [['C', (0,0,1)], ['C', (0,0.866025,0.5)], ['C', (0,0.866025,-0.5)],
['C', (0,0,-1)], ['C', (0,-0.866025,-0.5)], ['C', (0,-0.866025,0.5)]]

cube = [['C', (0,0,0)], ['Al', (1,0,0)], ['Al', (0,1,0)], ['Al', (0,0,1)], ['Al', (1,1,0)], ['Al', (1,0,1)], ['Al', (0,1,1)], ['C', (1,1,1)]]
center_mole(benzene)
#print(Coulomb_neighborhood(benzene))
#print(charge_inertia_tensor(benzene))
#print(charge_inertia_moment(benzene))
num_AEchildren(cube, m=7, dZ=[+1,1])
