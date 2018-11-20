import numpy as np
import matplotlib.pyplot as plt
import torch
import math

# CRUCIAL
# Compute loss function and write code for training the whole thing
# Make some data and test the whole thing out!!!

# NOT AS CRUCIAL
# Write embedding function for input grayscale images, imagined as a 2D grid of scalar values from [0,1]
# Write MPS compression function using iterated SVD's, make sure you don't backpropagate through 
#   the SVD though, sounds like this is numerically ill-conditioned
# Choose better initialization (potentially using above compression routine)
# Deal with variable local bond dimensions
# Deal with non-periodic boundary conditions
# Add placement of label index in any location

# REALLY MINOR
# Write code to move location of bond index


class SingleCore():
    def __init__(self, shape):
        # Initialize MPS core, which holds trainable core tensor
        D_l, D_r, d = shape
        self.shape = shape
        self.tensor = torch.randn(shape, dtype=torch.float)
        self.tensor.requires_grad = True
        
    def as_mat(self):
        # Reshape the D x D x d tensor into a (D*D) x d matrix
        D_l, D_r, d = self.shape
        return self.tensor.view((D_l*D_r, d))


class MPSClassifier():
    def __init__(self, size, D, d=2, num_labels=10, **args):
        """
        Define variables for holding our MPS cores (trainable)
        """
        # Number of sites in the MPS
        self.size = size
        # Global bond dimension
        self.D = D 
        # Dimension of local embedding space (one per pixel)
        self.d = d
        # Number of distinct labels for our classification
        self.num_labels = num_labels
        # Type of boundary conditions for our MPS, either 
        # 'open' or 'periodic' (default 'periodic')
        self.bc = 'periodic'
        if 'bc' in args.keys():
            self.bc = args['bc']

        # Shape of single MPS core
        self.shape = [D, D, d]
        # List of MPS cores, initialized randomly
        self.cores = [SingleCore(self.shape) for _ in range(size)]

        # The central label core, whose non-bond index gives
        # the output logit score for our classification labels
        self.label_core = SingleCore([D, D, num_labels])


    def _contract_input(self, input_vecs):
        """
        Contract input data with MPS cores and return 
        the resulting matrices as a torch tensor
        """

        # Massage the shape of the data vectors and core 
        # tensors, then batch multiply them together
        size, D, d = self.size, self.D, self.d
        input_vecs = input_vecs.view([size, d, 1])

        core_mats = [core.as_mat() for core in self.cores]
        core_mats = torch.stack(core_mats)

        matrices = torch.bmm(core_mats, input_vecs)
        return matrices.view([size, D, D])

    def logits(self, input_vecs):
        """
        Evaluate our classifier on the input data 
        and return a logit score over labels

        input_vecs must be formatted as a torch tensor
        """
        size, D, d = self.size, self.D, self.d
        num_labels = self.num_labels
        num_layers = math.ceil(math.log(size, 2))

        input_len = input_vecs.shape[0]
        input_d = input_vecs.shape[1]

        if input_len != size:
            raise ValueError(("len(input_vecs) = {0}, but "
                  "needs to be {1}").format(input_len, size))

        if input_d != d:
            raise ValueError(("dim(vec) = {0} in input_vecs, but "
                  "needs to be {1}").format(input_d, d))

        # I'm so far only considering power of 2 input sizes
        if (input_len & (input_len-1)) != 0:
            print("Sorry, but {} isn't a power of 2, and I'm lazy!".format(input_len))
            return

        # Inputs aren't trainable
        input_vecs.requires_grad = False

        # Get the matrices we multiply to get our logit scores
        mats = self._contract_input(input_vecs)
        new_size = size

        # Iteratively multiply nearest neighbor pairs of matrices
        # until we've reduced this to a single product matrix
        for j in range(num_layers):
            new_size = new_size // 2
            mats = mats.view([2, new_size, D, D])
            
            mats = torch.bmm(mats[0], mats[1])
        
        # Multiply our product matrix with the label tensor
        label_core = self.label_core.tensor.permute([2,0,1])
        mat_stack = mats[0].unsqueeze(0).expand([num_labels, D, D])
        logit_tensor = torch.bmm(mat_stack, label_core)
        
        # Take the partial trace over the bond indices, 
        # which leaves us with the output logit score
        logit_tensor = logit_tensor.view([num_labels, D*D])
        eye_vec = torch.eye(D).view(D*D)
        raw_score = torch.mv(logit_tensor, eye_vec)

        return raw_score


### TESTING STUFF BELOW ###
my_classifier = MPSClassifier(size=4, D=2, bc='open')

input_vecs = torch.FloatTensor([0, 1])
input_vecs = input_vecs.unsqueeze(0).expand([4, -1])

prediction = my_classifier.logits(input_vecs)

print(prediction)